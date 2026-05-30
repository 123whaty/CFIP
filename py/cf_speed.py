from __future__ import annotations

"""Cloudflare IP 连通性测速公共模块。

这个文件被 All/DE/US/JP/SG/NL 等地区脚本复用。各地区脚本只需要维护
IP 段和输出标签，真正的 CIDR 抽样、TCP 连接测速、排序和输出都集中在这里。

注意：这里测的是 GitHub Actions 运行环境到目标 IP:443 的 TCP 建连耗时。
Cloudflare 使用 Anycast，IP 上的国家标签只是订阅展示用，不代表真实落地机房。
"""

import ipaddress
import random          # 新增：用于随机抽样
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable, Sequence


DEFAULT_PORT = 443
DEFAULT_TIMEOUT = 3.0


@dataclass(frozen=True)
class ProbeResult:
    """单个 IP 的测速结果。

    latency_ms 为 None 表示连接失败或超时；有数字时表示 TCP 建连耗时。
    使用 dataclass 可以让后续排序和格式化代码更直观，也避免字典键拼写错误。
    """

    ip: str
    latency_ms: int | None

    @property
    def reachable(self) -> bool:
        return self.latency_ms is not None


def iter_sampled_ips(cidr_ranges: Sequence[str], sample_size: int) -> list[str]:
    """从每个 CIDR 网段里随机抽取 sample_size 个可用 IPv4 地址。

    通过 ipaddress 标准库解析 CIDR，跳过网络地址/广播地址，并对每个网段
    做 **随机无放回抽样**，自动去重，保证每次运行都能获得不同的 IP 集合。
    """

    seen: set[str] = set()
    ips: list[str] = []

    for cidr in cidr_ranges:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError as exc:
            print(f"跳过无效网段 {cidr}: {exc}", file=sys.stderr)
            continue

        # 收集该网段内所有可用的 IPv4 主机地址
        candidates = [
            str(addr) for addr in network.hosts() if addr.version == 4
        ]

        if not candidates:
            continue

        # 随机抽取指定数量的 IP（不超过候选数量）
        k = min(sample_size, len(candidates))
        chosen = random.sample(candidates, k)

        # 加入去重集合和结果列表
        for ip in chosen:
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)

    return ips


def probe_ip(ip: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
    """测试单个 IP 到指定端口的 TCP 建连耗时。

    connect_ex 不会在连接失败时抛异常，而是返回错误码；这样线程池里失败节点
    不会打断整批任务。这里不做 TLS 握手和下载测速，目的是保持运行快且依赖少。
    """

    start_time = time.perf_counter()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
    except OSError:
        return ProbeResult(ip=ip, latency_ms=None)

    if result != 0:
        return ProbeResult(ip=ip, latency_ms=None)

    latency_ms = int((time.perf_counter() - start_time) * 1000)
    return ProbeResult(ip=ip, latency_ms=latency_ms)


def probe_nodes(
    ips: Iterable[str],
    *,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
    max_workers: int = 3,
) -> list[ProbeResult]:
    """并发测试一组 IP。

    max_workers 会被限制到 IP 数量以内，避免空任务或过多线程。每个 future 都
    单独捕获异常，确保某个异常节点不会导致整个脚本没有输出。
    """

    ip_list = list(ips)
    if not ip_list:
        return []

    worker_count = max(1, min(max_workers, len(ip_list)))
    results: list[ProbeResult] = []

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(probe_ip, ip, port=port, timeout=timeout): ip
            for ip in ip_list
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                ip = futures[future]
                print(f"测试失败 {ip}: {exc}", file=sys.stderr)
                results.append(ProbeResult(ip=ip, latency_ms=None))

    return results


def fastest(results: Iterable[ProbeResult], limit: int) -> list[ProbeResult]:
    """筛出可连接节点，并按延迟从低到高取前 limit 个。"""

    reachable = [result for result in results if result.reachable]
    return sorted(reachable, key=lambda result: (result.latency_ms or 0, result.ip))[:limit]


def format_lines(
    results: Iterable[ProbeResult],
    suffix: str,
    *,
    include_latency: bool = False,
) -> list[str]:
    """把测速结果转换成仓库 .txt 文件需要的每行文本。

    suffix 由调用脚本传入，例如 "#de 【德国】 DE" 或 "#CF 优选IP"。
    workflow 会把 stdout 写入对应文件，因此这里不直接写磁盘。
    """

    lines: list[str] = []
    for result in results:
        latency = f" {result.latency_ms}ms" if include_latency else ""
        lines.append(f"{result.ip}{suffix}{latency}")
    return lines


def run_probe(
    cidr_ranges: Sequence[str],
    suffix: str,
    *,
    top_n: int = 30,
    sample_size: int = 9,
    max_workers: int = 3,
    timeout: float = DEFAULT_TIMEOUT,
    port: int = DEFAULT_PORT,
    include_latency: bool = False,
) -> int:
    """地区脚本的统一入口。

    执行顺序：CIDR 抽样 -> 并发测速 -> 取最快节点 -> 打印到 stdout。
    返回 0 表示脚本本身运行完成；如果没有可连接节点，会在 stderr 给出提示，
    由 GitHub Actions 判断 stdout 是否为空并决定是否覆盖旧文件。
    """

    ips = iter_sampled_ips(cidr_ranges, sample_size)
    if not ips:
        print("没有可测试的 IP", file=sys.stderr)
        return 0

    results = probe_nodes(ips, port=port, timeout=timeout, max_workers=max_workers)
    lines = format_lines(
        fastest(results, top_n),
        suffix,
        include_latency=include_latency,
    )

    for line in lines:
        print(line)

    if not lines:
        print("没有可连接的 IP", file=sys.stderr)

    return 0
