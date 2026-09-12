# sg-deadline

Deterministic legal deadline computation for Singapore. Rules are data, every answer comes
with a derivation trace, and the engine refuses to guess when it lacks holiday data.

Ships as a Python library, a CLI, and an [MCP](https://modelcontextprotocol.io) server so AI
assistants can *call* the arithmetic instead of attempting it.

```
$ sg-deadline compute sg.roc2021.defence 2026-03-13

rule sg.roc2021.defence: Defence to be filed and served (statement of claim served in Singapore)
source: Rules of Court 2021, O 6 r 7
trigger date: 2026-03-13 (Fri)
period: 21 days, direction: after
calendar-day count: 2026-03-13 (Fri) + 21 days = 2026-04-03 (Fri)
2026-04-03 (Fri) is a public holiday (Good Friday): rolled forward to next working day 2026-04-06 (Mon)
DEADLINE: 2026-04-06 (Mon)
holiday data SG 2026: UNVERIFIED, source=Ministry of Manpower gazetted public holidays 2026 (via data.gov.sg), retrieved=2026-09-12
```

## Why this exists

Deadline calculators are a SaaS category (LawToolbox, CourtDeadlines, Esquire). None are
open source, none cover Singapore, and none are callable by an AI assistant. Meanwhile LLMs
are routinely asked "when is the defence due?" and routinely get it wrong, because date
arithmetic with holiday exclusions is exactly the kind of thing language models fumble.

The fix is not a smarter prompt. It is to make the arithmetic deterministic, put it behind a
tool, and make the tool show its working.

## What it computes

| Tool | Governs | Notes |
|---|---|---|
| `compute_deadline` | Procedural periods (Rules of Court 2021) | Implements O 3 r 2: exclusive first day, short-period (<=7 day) exclusion of Sat/Sun/PH, clear days, roll to next working day |
| `limitation_deadline` | Limitation Act 1959 | Anniversary convention, longstops, deliberately **not** rolled |
| `deemed_receipt_date` | Contractual notice clauses | Cutoff times, business-day offsets, deferral on non-working days |
| `working_days_between`, `add_working_days`, `is_working_day` | Calendar utilities | Backed by vendored MOM public-holiday data |

## Install

```bash
pip install -e ".[dev]"       # library + CLI + tests
pip install -e ".[mcp]"       # adds the MCP server
```

Python 3.11+.

## CLI

```bash
sg-deadline rules                                          # list every rule, flagging unverified ones
sg-deadline compute sg.roc2021.defence 2026-03-13          # trace to stdout
sg-deadline --json compute sg.roc2021.defence 2026-03-13   # machine-readable
sg-deadline limitation sg.limitation.contract 2020-03-15
sg-deadline working-days 2026-12-23 2026-12-31
sg-deadline add-working-days 2026-12-24 3
sg-deadline deemed email 2026-03-13T18:05 --offset 1 --business-days --cutoff 17:00
```

Exit codes: `0` ok, `2` unknown rule, `3` holiday data missing for a year you touched.

## MCP server

```json
{
  "mcpServers": {
    "sg-deadline": {
      "command": "sg-deadline-mcp"
    }
  }
}
```

The server instructs the assistant to call `list_rules` first and pick a rule id explicitly,
so the *choice* of rule is visible in the transcript, not buried in the model's reasoning.
Every tool returns the full trace; the assistant should show it.

## Library

```python
from datetime import date
from sg_deadline import load_calendar, load_rules, compute

cal = load_calendar("SG")
rules = load_rules()
result = compute(rules["sg.roc2021.defence"], date(2026, 3, 13), cal)
print(result.deadline)        # 2026-04-06
print("\n".join(result.trace))
```

## Rules are data

```yaml
# rules/sg/roc2021.yaml
- id: sg.roc2021.defence
  source: "Rules of Court 2021, O 6 r 7"
  description: "Defence to be filed and served"
  period: { days: 21 }
  direction: after
  verified: false
  notes:
    - "Trigger is the date of service of the statement of claim."
```

Adding a rule is a YAML edit and a golden test. It never requires a Python change.

Every rule carries `verified: false` until a human has checked the period and provision
against the current text on [Singapore Statutes Online](https://sso.agc.gov.sg) and
recorded the check in `notes`. Unverified rules still compute, but emit a warning that is
returned to the caller and printed to stderr. **Do not flip `verified` to `true` in a PR
without citing what you checked and when.**

### Computation-of-time semantics (O 3 r 2)

| Sub-rule | Behaviour | Engine flag |
|---|---|---|
| (2) "within X after D" | day D excluded, count X, last day inclusive | `direction: after` |
| (3) "not less than X before D" | period ends immediately before D | `direction: before` |
| (4) "X clear days" | at least X whole days intervene | `clear_days: true` |
| (5) period <= 7 days | Sat/Sun/PH excluded from the count | `short_period_excludes_non_working` (default on) |
| (6) expiry on Sat/Sun/PH | act on next working day is in time | `roll: auto` (forward for *after*; **backward** for *before*, a conservative convention not in the rule text) |

Months and years use calendar arithmetic (Interpretation Act s 2); where the corresponding
date does not exist, the last day of the month is used and the trace says so.

## Holiday data

`data/holidays/sg-<year>.json`, one file per year, sourced from MOM via data.gov.sg. The
engine raises `HolidayDataMissingError` the moment a computation touches a year with no file.
This is intentional: a deadline engine that silently treats a public holiday as a working
day is worse than one that refuses to answer.

Refresh with `python scripts/refresh_holidays.py <year> <dataset_id>`; the file stays
`verified: false` until a human compares it to the gazette and re-runs with `--verified`.

## Scope and honesty

- **This is a calculation aid, not legal advice.** Every output carries the rule reference so
  it can be checked against the source. Check it.
- Court directions, consent orders and extensions override the default periods and are not
  modelled. The trigger date you supply must already reflect them.
- Limitation extensions (disability, fraud, acknowledgement, s 24A discretion) are not
  modelled; the trace says so.
- Only Singapore is bundled. The `rules/<jurisdiction>/` and `data/holidays/<jur>-<year>`
  layout is designed so other jurisdictions drop in without touching the engine.

## Contributing

Read `CLAUDE.md` for the engineering conventions (they apply to humans too). Short version:
rules in YAML, every rule change comes with a golden test computed by hand, no network calls
at compute time, never delete a trace line.

## Related projects

This engine is consumed by [oblig-register](https://github.com/kevanwee/oblig-register) (contract obligations to
calendar) and is designed to sit alongside [citecheck](https://github.com/kevanwee/citecheck),
[bundlebuild](https://github.com/kevanwee/bundlebuild), [chronology](https://github.com/kevanwee/chronology) and
[playbook-as-code](https://github.com/kevanwee/playbook-as-code).

## License

MIT.
