from cf_speed import run_probe


IP_RANGES = [
    "104.20.0.0/24",
    "188.114.96.0/24",
]


if __name__ == "__main__":
    raise SystemExit(run_probe(IP_RANGES, "#nl 【荷兰】 NL"))
