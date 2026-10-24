"""Show calendar coverage or refresh official published years; never computes legal dates."""

import os
import sys
from pathlib import Path

runtime = Path(__file__).resolve().parent.parent / "runtime"
if (runtime / "sg_deadline" / "__init__.py").is_file():
    sys.path.insert(0, str(runtime))

skill = runtime.parent
if (
    "SG_DEADLINE_CACHE" not in os.environ
    and skill.parent.name == "skills"
    and skill.parent.parent.name in {".agents", ".claude"}
):
    os.environ["SG_DEADLINE_CACHE"] = str(skill.parents[2] / ".legal-eng/calendars")

if __name__ == "__main__":
    from sg_deadline.calendar_cli import main
    raise SystemExit(main())
