from cf_speed import run_probe


# 日本分类展示用 IP 段。Cloudflare 为 Anycast，标签用于订阅名称展示。
IP_RANGES = [
    "108.162.198.0/22",
]


if __name__ == "__main__":
    # 这个网段历史上抽样 19 个地址，这里保留原有抽样规模。
    raise SystemExit(run_probe(IP_RANGES, "#jp 【日本】 JP", sample_size=19))
