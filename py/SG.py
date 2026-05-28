from cf_speed import run_probe


IP_RANGES = [
    "108.162.192.0/24",
    "162.159.0.0/24",
    "172.64.32.0/24",
]


if __name__ == "__main__":
    raise SystemExit(run_probe(IP_RANGES, "#sg 【新加坡】 SG"))
