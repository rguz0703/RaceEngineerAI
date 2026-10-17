"""Command-line entry point."""

import argparse
from collections.abc import Sequence

from raceengineer import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="raceengineer",
        description="RaceEngineerAI: telemetría y coaching para sim racing.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
