from cf_speed import run_probe


# 荷兰分类展示用 IP 段。Cloudflare 为 Anycast，标签用于订阅名称展示。
IP_RANGES = [
    "104.20.0.0/24",
    "188.114.96.0/24",
]


if __name__ == "__main__":
    # stdout 由 GitHub Actions 写入 NL.txt；脚本本身不直接写文件。
    raise SystemExit(run_probe(IP_RANGES, "#nl 【荷兰】 NL"))
