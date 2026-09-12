# CLAUDE.md — sg-deadline

Engineering conventions for this repository. They bind AI assistants and humans equally.

## What this is

A deterministic date-arithmetic engine for legal deadlines. The product is the **trace**:
a line-by-line derivation a lawyer can check against the rule text. Correctness is
provable; treat it that way.

## Non-negotiables

1. **No inference in the engine.** The library never guesses which rule applies, never
   parses prose, never calls a model. Rule selection is the caller's job and must be
   explicit (a rule id). If you feel the urge to add a "smart" lookup, stop; that belongs in
   a skill or the MCP client, not here.
2. **Never guess a holiday.** `Calendar` raises `HolidayDataMissingError` for uncovered years.
   Do not add a fallback that assumes "no holidays". Do not catch the exception inside the
   library.
3. **Never delete a trace line to tidy output.** Add lines freely; remove none. If output is
   too long for a UI, that UI truncates; the engine does not.
4. **Rules live in YAML, never in Python.** `rules.py` defines the schema; `rules/**/*.yaml`
   holds the content. A new rule is a YAML edit plus a golden test.
5. **No network at compute time.** Holiday refresh is a script run by a human and committed
   as a reviewable diff. The engine reads files only.
6. **`verified: true` requires evidence.** A PR that flips it must quote the provision
   checked and the date checked, in `notes`. Reviewers: reject otherwise.

## Layout

```
src/sg_deadline/
  calendar.py        working-day arithmetic; the only module that knows about holidays
  rules.py           Rule / Period / Direction models + YAML loader
  engine.py          compute(): pure function, produces Result with trace
  limitation.py      Limitation Act periods (separate semantics: years, no roll)
  deemed_receipt.py  contractual notice arithmetic
  cli.py             argparse front-end; thin
  server.py          FastMCP front-end; thin
  paths.py           single source of truth for data locations
rules/<jur>/*.yaml   rule content
data/holidays/       <jur>-<year>.json, one per year
scripts/             human-run maintenance (holiday refresh)
tests/               golden cases; expected values computed BY HAND
```

Front-ends (`cli.py`, `server.py`) contain no logic. If you find yourself computing a date
in either, move it into the library and test it there.

## Testing discipline

- Every test asserts a date that was **hand-derived** from the rule semantics. Write the
  derivation as a comment next to the assertion (see `test_engine.py`). If the engine and
  the hand derivation disagree, assume the engine is wrong until proven otherwise.
- A rule added without a golden test is an incomplete PR.
- Run `python -m pytest` before every commit. It takes under a second; there is no excuse.
- `ruff check src tests` must be clean.

## Style

- Python 3.11+, type hints everywhere, `from __future__ import annotations`.
- Pydantic v2 for anything loaded from YAML/JSON; dataclasses for internal results.
- Small pure functions. Side effects (file I/O) only in loaders and front-ends.
- Comments explain *why* (the legal rule, the convention chosen), not *what*. The code
  already says what.
- Line length 100. No clever one-liners where a loop reads clearer; correctness beats
  brevity in this codebase.

## Legal-content conventions

- Rule id format: `<jur>.<instrument>.<slug>`, lowercase, stable forever. Renaming an id is a
  breaking change; add a new id and leave the old one with a `notes` pointer instead.
- `source` is the citation a practitioner would write ("Rules of Court 2021, O 6 r 7").
- Where the engine adopts a **convention** rather than a rule (e.g. rolling *backward* for
  "before" periods, anniversary convention for limitation), say so in the trace text and in
  the README. Never present a convention as law.
- Do not model court discretion (extensions, directions). Document that the caller's
  trigger date must already reflect them.

## Adding a jurisdiction

1. `rules/<jur>/<instrument>.yaml` with `jurisdiction: <JUR>`.
2. `data/holidays/<jur>-<year>.json` for every year you expect to compute over.
3. If the computation-of-time semantics differ from ROC 2021 O 3 r 2, express the
   difference with the existing per-rule flags first. Only extend `Rule` if a flag cannot
   express it, and then add the flag with a default that preserves current behaviour.
4. Golden tests under `tests/test_<jur>_*.py`.

## Commit hygiene

- Conventional, imperative subject lines: `rules(sg): add O 9 r 17 summary judgment reply`.
- One logical change per commit. Rule additions and engine changes are never mixed.
- No AI attribution lines or co-author trailers in commit messages.

## What not to build here

- Clause extraction, NLP, anything reading a contract or judgment: that is
  `oblig-register`'s job. This repo receives structured parameters only.
- A web UI. The MCP server and CLI are the interfaces.
- Caching, async, or performance work. Every computation is microseconds.
