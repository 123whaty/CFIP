from __future__ import annotations

import ipaddress
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
    ip: str
    latency_ms: int | None

    @property
    def reachable(self) -> bool:
        return self.latency_ms is not None


def iter_sampled_ips(cidr_ranges: Sequence[str], sample_size: int) -> list[str]:
    """Return the first N usable IPv4 addresses from each CIDR range."""
    seen: set[str] = set()
    ips: list[str] = []

    for cidr in cidr_ranges:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError as exc:
            print(f"跳过无效网段 {cidr}: {exc}", file=sys.stderr)
            continue

        count = 0
        for address in network.hosts():
            if address.version != 4:
                continue

            ip = str(address)
            if ip in seen:
                continue

            seen.add(ip)
            ips.append(ip)
            count += 1

            if count >= sample_size:
                break

    return ips


def probe_ip(ip: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
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
    reachable = [result for result in results if result.reachable]
    return sorted(reachable, key=lambda result: (result.latency_ms or 0, result.ip))[:limit]


def format_lines(
    results: Iterable[ProbeResult],
    suffix: str,
    *,
    include_latency: bool = False,
) -> list[str]:
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
