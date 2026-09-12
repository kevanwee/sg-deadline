"""Command-line interface. Thin: parse args, call the library, print the trace."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime

from . import (
    DeemedReceiptRule,
    HolidayDataMissingError,
    compute,
    deemed_receipt,
    limitation_period,
    load_calendar,
    load_limitation_rules,
    load_rules,
)
from .engine import Result


def _print(result: Result, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return
    for line in result.trace:
        print(line)
    for w in result.warnings:
        print(f"WARNING: {w}", file=sys.stderr)


def cmd_compute(args: argparse.Namespace) -> int:
    rules = load_rules()
    if args.rule_id not in rules:
        print(f"unknown rule {args.rule_id!r}; run `sg-deadline rules`", file=sys.stderr)
        return 2
    cal = load_calendar(args.jurisdiction)
    _print(compute(rules[args.rule_id], date.fromisoformat(args.trigger), cal), args.json)
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    rules = load_rules()
    for r in rules.values():
        if args.tag and args.tag not in r.tags:
            continue
        flag = "" if r.verified else " [unverified]"
        print(f"{r.id:40} {str(r.period):14} {r.direction.value:6} {r.description}{flag}")
    lims = load_limitation_rules()
    if lims:
        print()
        for lr in lims.values():
            flag = "" if lr.verified else " [unverified]"
            print(f"{lr.id:40} {lr.years} years from {lr.runs_from:9} {lr.description}{flag}")
    return 0


def cmd_limitation(args: argparse.Namespace) -> int:
    lims = load_limitation_rules()
    if args.rule_id not in lims:
        print(f"unknown limitation rule {args.rule_id!r}", file=sys.stderr)
        return 2
    cal = load_calendar(args.jurisdiction)
    _print(limitation_period(lims[args.rule_id], date.fromisoformat(args.start), cal),
           args.json)
    return 0


def cmd_working_days(args: argparse.Namespace) -> int:
    cal = load_calendar(args.jurisdiction)
    a, b = date.fromisoformat(args.start), date.fromisoformat(args.end)
    print(cal.working_days_between(a, b))
    return 0


def cmd_add_working_days(args: argparse.Namespace) -> int:
    cal = load_calendar(args.jurisdiction)
    print(cal.add_working_days(date.fromisoformat(args.start), args.n).isoformat())
    return 0


def cmd_deemed(args: argparse.Namespace) -> int:
    cal = load_calendar(args.jurisdiction)
    rule = DeemedReceiptRule(
        method=args.method,
        offset_days=args.offset,
        business_days=args.business_days,
        cutoff=datetime.strptime(args.cutoff, "%H:%M").time() if args.cutoff else None,
        non_working_day_defers=args.defer_non_working,
        roll_to_working_day=args.roll,
    )
    _print(deemed_receipt(rule, datetime.fromisoformat(args.sent_at), cal), args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sg-deadline",
                                description="Deterministic legal deadline computation.")
    p.add_argument("--jurisdiction", "-j", default="SG")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a trace")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compute", help="apply a rule to a trigger date")
    c.add_argument("rule_id")
    c.add_argument("trigger", help="ISO date, e.g. 2026-03-13")
    c.set_defaults(fn=cmd_compute)

    r = sub.add_parser("rules", help="list available rules")
    r.add_argument("--tag")
    r.set_defaults(fn=cmd_rules)

    lim = sub.add_parser("limitation", help="limitation period from accrual/knowledge date")
    lim.add_argument("rule_id")
    lim.add_argument("start")
    lim.set_defaults(fn=cmd_limitation)

    wd = sub.add_parser("working-days", help="working days after start up to and incl. end")
    wd.add_argument("start")
    wd.add_argument("end")
    wd.set_defaults(fn=cmd_working_days)

    awd = sub.add_parser("add-working-days", help="date n working days from start")
    awd.add_argument("start")
    awd.add_argument("n", type=int)
    awd.set_defaults(fn=cmd_add_working_days)

    d = sub.add_parser("deemed", help="deemed receipt of a contractual notice")
    d.add_argument("method")
    d.add_argument("sent_at", help="ISO datetime, e.g. 2026-03-13T18:05")
    d.add_argument("--offset", type=int, default=0)
    d.add_argument("--business-days", action="store_true")
    d.add_argument("--cutoff", help="HH:MM local time")
    d.add_argument("--defer-non-working", action="store_true")
    d.add_argument("--roll", action="store_true")
    d.set_defaults(fn=cmd_deemed)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except HolidayDataMissingError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
