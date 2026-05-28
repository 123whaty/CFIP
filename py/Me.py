import re
import sys
from typing import List, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup


# Me.txt 数据源。页面结构可能调整，所以解析代码同时支持表格和列表/卡片兜底。
URL = "https://api.uouin.com/cloudflare.html"


def normalize_speed_to_bps(speed_text: str) -> Optional[float]:
    """把页面里的速度文本转换成 bytes/s。

    支持 B/s、KB/s、MB/s、GB/s，也兼容 Mb/s、MBps 和中文“每秒”等写法。
    返回 None 表示无法解析；排序时这类结果会放到末尾。
    """
    if not speed_text:
        return None

    text = speed_text.strip()
    # Replace Chinese characters commonly used
    text = text.replace("每秒", "/s").replace("秒", "/s")
    # Standardize separators
    text = text.replace("/sec", "/s").replace("/秒", "/s").replace("ps", "/s")

    # Extract number and unit
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMG]?)([bB])(?:it)?\s*/?s", text)
    if not m:
        # Try without explicit per-second, assume per second
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMG]?)([bB])", text)
        if not m:
            return None

    value = float(m.group(1))
    prefix = m.group(2).upper()  # '', 'K', 'M', 'G'
    byte_or_bit = m.group(3)

    multiplier = 1.0
    if prefix == "K":
        multiplier = 1024.0
    elif prefix == "M":
        multiplier = 1024.0 ** 2
    elif prefix == "G":
        multiplier = 1024.0 ** 3

    bps = value * multiplier
    # If unit captured was lowercase 'b' (bit), convert to bytes
    if byte_or_bit == "b":  # bit
        bps = bps / 8.0

    return bps


def extract_table_data(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """优先从表格中提取 IP、线路和速度。

    表头不一定固定，所以用关键词识别列位置；如果没有表头，则尝试用第一行判断。
    返回统一字典结构，方便后续与列表兜底结果合并。
    """

    data: List[Dict[str, str]] = []
    ip_regex = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    for table in soup.find_all(["table"]):
        # Identify headers if present
        headers: List[str] = []
        thead = table.find("thead")
        if thead:
            ths = thead.find_all("th")
            headers = [th.get_text(strip=True) for th in ths]
        else:
            # Try first row as header if contains non-IP words
            first_tr = table.find("tr")
            if first_tr:
                cells = [c.get_text(strip=True) for c in first_tr.find_all(["td", "th"])]
                if cells and not ip_regex.search(" ".join(cells)):
                    headers = cells

        # Map likely indices
        idx_ip = idx_line = idx_speed = None
        if headers:
            for i, h in enumerate(headers):
                if idx_ip is None and ("IP" in h.upper() or ip_regex.search(h)):
                    idx_ip = i
                if idx_line is None and any(k in h for k in ["线路", "运营商", "地区", "域"]):
                    idx_line = i
                if idx_speed is None and any(k in h for k in ["速度", "下载", "带宽", "Speed", "速率"]):
                    idx_speed = i

        # Iterate body rows
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])  # include th in case no thead
            if not tds:
                continue

            texts = [td.get_text(strip=True) for td in tds]
            # Try to identify IP cell
            ip: Optional[str] = None
            line: Optional[str] = None
            speed: Optional[str] = None

            if idx_ip is not None and idx_ip < len(texts):
                ip_match = ip_regex.search(texts[idx_ip])
                if ip_match:
                    ip = ip_match.group(0)
            else:
                # Fallback: search any cell for an IP address
                for txt in texts:
                    ip_match = ip_regex.search(txt)
                    if ip_match:
                        ip = ip_match.group(0)
                        break

            if ip is None:
                continue

            if idx_line is not None and idx_line < len(texts):
                line = texts[idx_line]
            else:
                # Heuristic: pick a cell with Chinese characters near IP cell
                for txt in texts:
                    if txt != ip and re.search(r"[\u4e00-\u9fa5]", txt):
                        line = txt
                        break

            if idx_speed is not None and idx_speed < len(texts):
                speed = texts[idx_speed]
            else:
                # Heuristic: pick a cell containing units
                for txt in texts:
                    if re.search(r"\b[0-9]+(?:\.[0-9]+)?\s*[KMG]?[bB](?:it)?(?:/s|ps)?\b", txt):
                        speed = txt
                        break

            data.append({
                "ip": ip,
                "line": (line or "").strip() or "未知",
                "speed": (speed or "").strip() or "",
            })

    return data


def extract_list_items(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """表格解析失败时，从列表/段落/卡片文本里兜底提取结果。"""

    data: List[Dict[str, str]] = []
    ip_regex = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    candidates = soup.find_all(["li", "p", "div", "span"])

    for el in candidates:
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        ip_match = ip_regex.search(text)
        if not ip_match:
            continue
        ip = ip_match.group(0)

        # Try to split by separators and detect fields
        parts = re.split(r"[|｜、，,；;\s]+", text)
        line_val = None
        speed_val = None
        for p in parts:
            if ip in p:
                continue
            if line_val is None and re.search(r"线路|运营商|地区|联通|电信|移动|香港|日本|美国|西雅图|新加坡", p):
                line_val = re.sub(r"^(线路|运营商|地区)[:：]\s*", "", p)
            if speed_val is None and re.search(r"下载|速度|[KMG]?[bB](?:it)?(?:/s|ps)?", p):
                speed_val = re.sub(r"^(下载|速度|带宽)[:：]\s*", "", p)

        data.append({
            "ip": ip,
            "line": (line_val or "").strip() or "未知",
            "speed": (speed_val or "").strip() or "",
        })

    return data


def fetch_html(url: str) -> str:
    """抓取数据源页面。

    第一次请求忽略环境代理，第二次允许环境代理，兼顾 GitHub Actions 和本地运行。
    两次都失败时抛出最后一次异常，由 main 打印错误并返回非 0。
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    last_error: Exception | None = None
    # attempt 0: bypass environment proxies; attempt 1: allow environment proxies
    for attempt in range(2):
        try:
            with requests.Session() as s:
                s.headers.update(headers)
                if attempt == 0:
                    # Bypass any system proxy that could block the request
                    s.trust_env = False
                    s.proxies = {}
                resp = s.get(url, timeout=20)
                resp.raise_for_status()
                return resp.text
        except Exception as e:
            last_error = e
            continue
    assert last_error is not None
    raise last_error


def parse_and_sort(html: str) -> List[Tuple[str, str, str, float]]:
    """解析 HTML、按 IP 去重，并按速度从高到低排序。"""

    soup = BeautifulSoup(html, "lxml")

    rows = extract_table_data(soup)
    if not rows:
        rows = extract_list_items(soup)

    # Deduplicate by IP, prefer rows with a parseable speed
    ip_to_best: Dict[str, Dict[str, str]] = {}
    for r in rows:
        ip = r.get("ip", "").strip()
        if not ip:
            continue
        speed_bps = normalize_speed_to_bps(r.get("speed", ""))
        if ip not in ip_to_best:
            ip_to_best[ip] = {**r, "_bps": speed_bps if speed_bps is not None else -1.0}
        else:
            prev_bps = ip_to_best[ip]["_bps"]
            cand_bps = speed_bps if speed_bps is not None else -1.0
            if cand_bps > prev_bps:
                ip_to_best[ip] = {**r, "_bps": cand_bps}

    result: List[Tuple[str, str, str, float]] = []
    for ip, r in ip_to_best.items():
        bps = r.get("_bps")
        bps_val = float(bps) if isinstance(bps, (int, float)) else -1.0
        result.append((ip, r.get("line", "未知"), r.get("speed", ""), bps_val))

    # Sort by parsed speed descending; unknown speeds go to the end
    result.sort(key=lambda x: (x[3] if x[3] is not None else -1.0), reverse=True)
    return result


def format_results(rows: List[Tuple[str, str, str, float]]) -> List[str]:
    """转换为 Me.txt 的每行文本格式。"""

    return [
        f"{ip}#【{line or '未知'} Nodes】{speed_text or ''}"
        for ip, line, speed_text, _ in rows
    ]


def main() -> int:
    """生成 Me.txt 的内容并输出到 stdout。"""

    try:
        html = fetch_html(URL)
    except Exception as e:
        print(f"请求失败: {e}")
        return 2

    rows = parse_and_sort(html)
    if not rows:
        print("未从页面中解析到任何数据。")
        return 1

    for line in format_results(rows):
        print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
