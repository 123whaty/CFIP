from cf_speed import run_probe


IP_RANGES = [
    "104.16.0.0/22",
    "104.18.0.0/22",
    "104.19.0.0/22",
    "104.17.0.0/22",
    "103.31.4.0/22",
    "103.21.244.0/22",
]


if __name__ == "__main__":
    raise SystemExit(run_probe(IP_RANGES, "#us 【美国】 US"))
