from cf_speed import run_probe


IP_RANGES = [
    "108.162.198.0/22",
]


if __name__ == "__main__":
    raise SystemExit(run_probe(IP_RANGES, "#jp 【日本】 JP", sample_size=19))
