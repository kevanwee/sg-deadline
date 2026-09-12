"""MCP server exposing the engine to AI assistants.

Every tool returns the full derivation trace. The assistant is expected to show the trace
to the user, not just the date. Tools never infer rule ids from prose; the assistant must
call `list_rules` and pick one explicitly, so the choice of rule is visible and auditable.
"""

from __future__ import annotations

from datetime import date, datetime, time

try:  # mcp >= 2.0 renamed FastMCP -> MCPServer; same decorator/run surface
    from mcp.server.mcpserver import MCPServer as FastMCP
except ModuleNotFoundError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from . import (
    DeemedReceiptRule,
    compute,
    deemed_receipt,
    limitation_period,
    load_calendar,
    load_limitation_rules,
    load_rules,
)

mcp = FastMCP(
    "sg-deadline",
    instructions=(
        "Deterministic legal deadline calculator for Singapore. Always call list_rules first, "
        "choose a rule id explicitly, then compute_deadline. Present the full trace to the "
        "user and repeat any warnings verbatim. Never compute dates yourself."
    ),
)

_RULES = load_rules()
_LIMITATION = load_limitation_rules()
_CAL = {"SG": load_calendar("SG")}


def _cal(jurisdiction: str):
    j = jurisdiction.upper()
    if j not in _CAL:
        _CAL[j] = load_calendar(j)
    return _CAL[j]


@mcp.tool()
def list_rules(tag: str | None = None) -> list[dict]:
    """List procedural rules (Rules of Court etc.) and limitation rules with their ids."""
    out = []
    for r in _RULES.values():
        if tag and tag not in r.tags:
            continue
        out.append({
            "id": r.id, "kind": "procedural", "description": r.description,
            "source": r.source, "period": str(r.period), "direction": r.direction.value,
            "clear_days": r.clear_days, "verified": r.verified, "tags": r.tags,
        })
    for lr in _LIMITATION.values():
        out.append({
            "id": lr.id, "kind": "limitation", "description": lr.description,
            "source": lr.source, "period": f"{lr.years} years", "runs_from": lr.runs_from,
            "verified": lr.verified,
        })
    return out


@mcp.tool()
def compute_deadline(rule_id: str, trigger_date: str, jurisdiction: str = "SG") -> dict:
    """Apply a procedural rule to a trigger date (ISO yyyy-mm-dd). Returns deadline + trace."""
    if rule_id not in _RULES:
        return {"error": f"unknown rule id {rule_id!r}; call list_rules"}
    return compute(_RULES[rule_id], date.fromisoformat(trigger_date), _cal(jurisdiction)).to_dict()


@mcp.tool()
def limitation_deadline(rule_id: str, start_date: str, jurisdiction: str = "SG") -> dict:
    """Last day to commence proceedings under a limitation rule, from accrual/knowledge date."""
    if rule_id not in _LIMITATION:
        return {"error": f"unknown limitation rule id {rule_id!r}; call list_rules"}
    return limitation_period(_LIMITATION[rule_id], date.fromisoformat(start_date),
                             _cal(jurisdiction)).to_dict()


@mcp.tool()
def working_days_between(start_date: str, end_date: str, jurisdiction: str = "SG") -> dict:
    """Working days strictly after start up to and including end."""
    cal = _cal(jurisdiction)
    a, b = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return {"working_days": cal.working_days_between(a, b), "notes": cal.coverage_notes(a, b)}


@mcp.tool()
def add_working_days(start_date: str, n: int, jurisdiction: str = "SG") -> dict:
    """Date that is n working days after (or before, if negative) start."""
    cal = _cal(jurisdiction)
    a = date.fromisoformat(start_date)
    d = cal.add_working_days(a, n)
    return {"date": d.isoformat(), "weekday": d.strftime("%A"), "notes": cal.coverage_notes(a, d)}


@mcp.tool()
def is_working_day(day: str, jurisdiction: str = "SG") -> dict:
    """Whether a date is a working day; if not, why."""
    cal = _cal(jurisdiction)
    d = date.fromisoformat(day)
    return {"date": d.isoformat(), "working": cal.is_working(d), "reason": cal.why_non_working(d)}


@mcp.tool()
def deemed_receipt_date(
    method: str,
    sent_at: str,
    offset_days: int = 0,
    business_days: bool = False,
    cutoff: str | None = None,
    non_working_day_defers: bool = False,
    roll_to_working_day: bool = False,
    clause_ref: str = "",
    verbatim: str = "",
    jurisdiction: str = "SG",
) -> dict:
    """Deemed receipt of a contractual notice. Express the clause as parameters; sent_at is
    an ISO datetime; cutoff is HH:MM. Include the clause wording in `verbatim` for the audit
    trail."""
    rule = DeemedReceiptRule(
        method=method, offset_days=offset_days, business_days=business_days,
        cutoff=time.fromisoformat(cutoff) if cutoff else None,
        non_working_day_defers=non_working_day_defers, roll_to_working_day=roll_to_working_day,
        clause_ref=clause_ref, verbatim=verbatim,
    )
    return deemed_receipt(rule, datetime.fromisoformat(sent_at), _cal(jurisdiction)).to_dict()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
