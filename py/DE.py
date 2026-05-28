from cf_speed import run_probe


IP_RANGES = [
    "188.114.96.0/20",
    "104.21.0.0/24",
    "104.24.0.0/24",
    "104.25.0.0/24",
    "104.27.0.0/24",
    "104.26.0.0/24",
]


if __name__ == "__main__":
    raise SystemExit(run_probe(IP_RANGES, "#de 【德国】 DE"))
