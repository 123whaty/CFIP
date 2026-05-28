from cf_speed import run_probe


# 新加坡分类展示用 IP 段。Cloudflare 为 Anycast，标签用于订阅名称展示。
IP_RANGES = [
    "108.162.192.0/24",
    "162.159.0.0/24",
    "172.64.32.0/24",
]


if __name__ == "__main__":
    # stdout 由 GitHub Actions 写入 SG.txt；脚本本身不直接写文件。
    raise SystemExit(run_probe(IP_RANGES, "#sg 【新加坡】 SG"))
