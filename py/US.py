from cf_speed import run_probe


# 美国分类展示用 IP 段。Cloudflare 为 Anycast，标签用于订阅名称展示。
IP_RANGES = [
    "104.16.0.0/22",
    "104.18.0.0/22",
    "104.19.0.0/22",
    "104.17.0.0/22",
    "103.31.4.0/22",
    "103.21.244.0/22",
]


if __name__ == "__main__":
    # stdout 由 GitHub Actions 写入 US.txt；脚本本身不直接写文件。
    raise SystemExit(run_probe(IP_RANGES, "#us 【美国】 US"))
