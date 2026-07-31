"""Generate JSON schemas for contract models.

Stub until increment 2 registers the first contract; `--check` must exit 0.
"""

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate JSON schemas for contract models.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed schemas match regenerated output",
    )
    parser.parse_args()
    print("no contracts registered yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
