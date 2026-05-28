import re
import sys
import urllib.request
from html.parser import HTMLParser
from urllib.error import URLError, HTTPError


# cfxyz 数据源页面，脚本会解析 HTML 表格中的 IP 和测速值。
URL = "https://ip.164746.xyz/"


def fetch_text(url: str, timeout_seconds: float = 10.0) -> str:
    """获取页面文本。

    使用 urllib 标准库避免额外依赖；显式设置 User-Agent，减少被源站当作异常请求
    拒绝的概率。返回值按页面声明的 charset 解码。
    """

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            )
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


# IPv4 正则会限制每段 0-255，避免普通数字串被误判成 IP。
IPV4_PATTERN = r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"

# 简化 IPv6 匹配器：覆盖常见完整写法和压缩写法，足够用于页面文本提取。
IPV6_PATTERN = (
    r"\b("  # start group to keep one full match
    r"(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}|"  # 1:2:3:4:5:6:7:8
    r"(?:[A-Fa-f0-9]{1,4}:){1,7}:|"               # 1::    to 1:2:3:4:5:6:7::
    r"::(?:[A-Fa-f0-9]{1,4}:){1,7}[A-Fa-f0-9]{1,4}|"  # ::1   to ::1:2:3:4:5:6:7:8
    r"(?:[A-Fa-f0-9]{1,4}:){1,6}:[A-Fa-f0-9]{1,4}|"   # 1::8  to 1:2:3:4:5:6::8
    r"(?:[A-Fa-f0-9]{1,4}:){1,5}(?::[A-Fa-f0-9]{1,4}){1,2}|"  # 1::7:8 etc
    r"(?:[A-Fa-f0-9]{1,4}:){1,4}(?::[A-Fa-f0-9]{1,4}){1,3}|"
    r"(?:[A-Fa-f0-9]{1,4}:){1,3}(?::[A-Fa-f0-9]{1,4}){1,4}|"
    r"(?:[A-Fa-f0-9]{1,4}:){1,2}(?::[A-Fa-f0-9]{1,4}){1,5}|"
    r"[A-Fa-f0-9]{1,4}:(?::[A-Fa-f0-9]{1,4}){1,6}|"
    r":(?::[A-Fa-f0-9]{1,4}){1,7}|"                # :1:2:3:4:5:6:7 (rare in text)
    r"::"                                           # :: (unspecified)
    r")\b"
)


# 速度字段可能以 MB/s、Mbps、KiB/s 等形式出现；后续会转换成统一单位排序。
SPEED_PATTERN = (
    r"\b\d+(?:\.\d+)?\s?(?:"
    r"[KMG]?i?B/s|[KMG]B/s|B/s|"
    r"[KMG]?bps|Gbps|Mbps|Kbps|bps"
    r")\b"
)


class _TableRowExtractor(HTMLParser):
    """轻量表格解析器。

    只关心 table/tr/td/th 中的纯文本，忽略 script/style。相比整页正则匹配，
    行级解析能更好地把同一行里的 IP 和速度关联起来。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_table = False
        self._in_ignored = 0  # depth counter for script/style
        self._in_row = False
        self._in_cell = False
        self._current_cell_parts: list[str] = []
        self._current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self._in_table = True
        elif tag in {"script", "style"}:
            self._in_ignored += 1
        if not self._in_table or self._in_ignored:
            return
        if tag == "tr":
            self._in_row = True
            self._current_row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._current_cell_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "table":
            self._in_table = False
        elif tag in {"script", "style"} and self._in_ignored > 0:
            self._in_ignored -= 1
        if not self._in_table or self._in_ignored:
            return
        if tag in {"td", "th"} and self._in_row and self._in_cell:
            cell_text = "".join(self._current_cell_parts).strip()
            self._current_row.append(cell_text)
            self._in_cell = False
            self._current_cell_parts = []
        elif tag == "tr" and self._in_row:
            # finalize row only if any cell captured
            if self._current_row:
                self.rows.append(self._current_row)
            self._in_row = False
            self._current_row = []

    def handle_data(self, data):
        if self._in_table and self._in_row and self._in_cell and self._in_ignored == 0:
            self._current_cell_parts.append(data)


def extract_ip_speed_pairs(html: str) -> list[tuple[str, str]]:
    """从 HTML 表格中提取唯一 IP 和对应速度文本。"""

    parser = _TableRowExtractor()
    parser.feed(html)

    pairs: list[tuple[str, str]] = []
    seen_ips: set[str] = set()

    for row in parser.rows:
        row_text = " ".join(row)
        ips_in_row = re.findall(IPV4_PATTERN, row_text) + re.findall(IPV6_PATTERN, row_text)
        if not ips_in_row:
            continue
        speed_match = re.search(SPEED_PATTERN, row_text)
        speed_value = speed_match.group(0) if speed_match else ""
        for ip in ips_in_row:
            if ip in seen_ips:
                continue
            seen_ips.add(ip)
            pairs.append((ip, speed_value))

    return pairs


def _parse_speed_to_bps(speed_text: str) -> float:
    """将速度文本转换为 bit/s，用于从快到慢排序。

    解析失败返回 -1，让没有速度的 IP 自动排在最后。
    """

    if not speed_text:
        return -1.0

    text = speed_text.strip()

    m = re.match(r"^(\d+(?:\.\d+)?)[\s]*([A-Za-z/]+)$", text)
    if not m:
        return -1.0

    value = float(m.group(1))
    unit = m.group(2)

    u = unit.replace(" ", "")
    ul = u.lower()

    # Bits per second units (bps, Kbps, Mbps, Gbps)
    if ul.endswith("bps"):
        prefix = ul[:-3]
        scale = 1.0
        if prefix == "k":
            scale = 1e3
        elif prefix == "m":
            scale = 1e6
        elif prefix == "g":
            scale = 1e9
        return value * scale

    # Byte per second units (/s). Handle binary (KiB/s, MiB/s, GiB/s) and decimal (KB/s, MB/s, GB/s)
    if ul.endswith("ib/s"):
        # Binary bytes per second -> convert bytes to bits (x8)
        prefix = ul[:-4]  # remove 'iB/s', leaves k/m/g
        bytes_scale = 1.0
        if prefix == "k":
            bytes_scale = 1024.0
        elif prefix == "m":
            bytes_scale = 1024.0 ** 2
        elif prefix == "g":
            bytes_scale = 1024.0 ** 3
        return value * bytes_scale * 8.0

    if ul.endswith("b/s"):
        # Decimal bytes per second -> convert bytes to bits (x8)
        prefix = ul[:-3]  # remove 'B/s' or 'b/s'
        bytes_scale = 1.0
        if prefix == "k":
            bytes_scale = 1e3
        elif prefix == "m":
            bytes_scale = 1e6
        elif prefix == "g":
            bytes_scale = 1e9
        return value * bytes_scale * 8.0

    return -1.0


def main() -> int:
    """抓取 cfxyz 页面并输出 Cfxyz.txt 内容。"""

    try:
        content = fetch_text(URL)
    except HTTPError as http_err:
        print(f"HTTP error: {http_err.code} {http_err.reason}", file=sys.stderr)
        return 1
    except URLError as url_err:
        print(f"Network error: {url_err.reason}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    pairs = extract_ip_speed_pairs(content)
    if not pairs:
        print("No IP addresses (with speeds) found inside HTML tables", file=sys.stderr)
        return 2

    # sort by parsed speed (bps) descending; IPs without speed go last
    sorted_pairs = sorted(
        pairs,
        key=lambda p: _parse_speed_to_bps(p[1]),
        reverse=True,
    )

    # print to stdout
    for ip, speed in sorted_pairs:
        print(f"{ip}#【测速 Nodes】{speed}".strip())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
