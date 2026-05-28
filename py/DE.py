from cf_speed import run_probe


# 德国分类展示用 IP 段。Cloudflare 为 Anycast，标签用于订阅名称展示。
IP_RANGES = [
    "188.114.96.0/20",
    "104.21.0.0/24",
    "104.24.0.0/24",
    "104.25.0.0/24",
    "104.27.0.0/24",
    "104.26.0.0/24",
]


if __name__ == "__main__":
    # stdout 由 GitHub Actions 写入 DE.txt；脚本本身不直接写文件。
    raise SystemExit(run_probe(IP_RANGES, "#de 【德国】 DE"))
