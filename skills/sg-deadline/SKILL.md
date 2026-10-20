---
name: sg-deadline
description: Compute Singapore legal deadlines deterministically, such as Rules of Court 2021 time periods, Limitation Act 1959 periods and contractual deemed receipt, with a derivation trace. Use whenever a Singapore procedural deadline, limitation date or notice receipt date is needed; never do the date arithmetic in prose.
---

# Singapore deadlines

Language models get date arithmetic wrong in exactly the places that matter: excluded days,
short-period rules, public holidays and rolling to the next working day. This skill makes the
arithmetic deterministic. The `sg-deadline` engine computes the date from an explicitly chosen
rule and shows every step. Your job is to choose the rule and trigger date correctly, run the
engine, and report its result and limits faithfully.

## Make the engine available

The engine is a Python package. If `python -m sg_deadline.cli --help` fails, install the
pinned revision recorded in this skill's `TOOLKIT-SOURCE.json`, or the revision the user names:

```sh
python -m pip install "sg-deadline @ git+https://github.com/kevanwee/sg-deadline@<revision>"
```

Installation needs network access and the user's permission. If either is missing, stop and
say so; do not compute the date yourself instead. The MCP server (`sg-deadline-mcp`) is an
alternative where the host has it configured.

## Choose the rule and trigger

1. List the rules: `python -m sg_deadline.cli rules`. Each has an id, its source provision,
   and whether it has been verified against the current text.
2. Establish the trigger date from the facts: the date of service, of the judgment, of the
   breach, or of sending a notice, as the rule requires. Read each rule's notes; they state its
   trigger and when a different rule applies, such as service out of Singapore.
3. If the facts do not determine one rule or one trigger date, ask. Do not pick the more
   convenient reading. A wrong rule produces a precise, wrong date.
4. Record the choice and why. In a workflow, the rule and trigger come from task inputs that a
   person or an earlier reviewed task supplied.

## Compute and report

Use the bundled adapter, which calls the engine and returns the workflow's computation
contract:

```sh
python <this skill>/scripts/contract.py compute <rule-id> <YYYY-MM-DD>
python <this skill>/scripts/contract.py limitation <rule-id> <YYYY-MM-DD>
```

The output carries the date, the rule's source and verification status, the full trace, the
holiday years touched with their verification status, the engine revision, and limitations.
Exit code 3 means holiday data is missing for a year the computation touches: report that the
date cannot be computed, and do not assume there are no holidays.

Report the date with its trace. Lead with any limitation: an unverified rule or holiday year
must be checked against Singapore Statutes Online or the gazetted holiday list before the date
is relied upon. A limitation date is the last day to commence proceedings and is not rolled
forward to a working day; say so where it falls on a non-working day.

## Boundaries

This skill computes dates. It does not decide which proceedings to bring, whether time has
been extended by agreement or order, or whether a limitation defence applies. Court orders and
extensions change the trigger or the period; the person responsible must supply them. Never
file, serve or send anything.
