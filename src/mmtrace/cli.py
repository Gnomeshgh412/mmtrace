"""Command line interface for MMTrace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from mmtrace.adapters.base import AdapterError
from mmtrace.adapters.browser_use import BrowserUseAdapter
from mmtrace.adapters.generic_json import GenericJSONAdapter
from mmtrace.adapters.holo4 import Holo4Adapter
from mmtrace.adapters.osworld import OSWorldAdapter
from mmtrace.engine import DEFAULT_CHECKS, CheckEngine
from mmtrace.report import format_report
from mmtrace.schema.finding import ReportStatus


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        return run_check(args, stderr=sys.stderr)

    parser.print_help(sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mmtrace")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="check an MMTrace JSON trajectory")
    check_parser.add_argument("input", help="path to an MMTrace JSON trajectory")
    check_parser.add_argument(
        "--adapter",
        choices=["generic", "browser-use", "osworld", "holo4"],
        default="generic",
    )
    check_parser.add_argument("--format", choices=["text", "json"], default="text")
    check_parser.add_argument("--output", help="write report to this path")
    check_parser.add_argument("--rule", help="run only the specified rule ID")

    return parser


def run_check(args: argparse.Namespace, stderr: TextIO) -> int:
    checks = list(DEFAULT_CHECKS)

    if args.rule:
        checks = [check for check in checks if check.rule_id == args.rule]
        if not checks:
            print(f"MMTrace error: unknown rule ID: {args.rule}", file=stderr)
            return 2

    adapter = _adapter_for_name(args.adapter)

    try:
        trace = adapter.load(args.input)
    except AdapterError as exc:
        print(f"MMTrace error: {exc}", file=stderr)
        return 2

    report = CheckEngine(checks=checks).run(trace)
    rendered = format_report(report, args.format)

    if args.output:
        output_path = Path(args.output)
        try:
            output_path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"MMTrace error: failed to write {output_path}: {exc}", file=stderr)
            return 2
    else:
        print(rendered)

    return 1 if report.status is ReportStatus.FAIL else 0


def _adapter_for_name(name: str):
    if name == "generic":
        return GenericJSONAdapter()
    if name == "browser-use":
        return BrowserUseAdapter()
    if name == "osworld":
        return OSWorldAdapter()
    if name == "holo4":
        return Holo4Adapter()
    raise ValueError(f"unsupported adapter: {name}")


if __name__ == "__main__":
    raise SystemExit(main())
