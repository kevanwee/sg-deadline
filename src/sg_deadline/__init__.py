"""sg-deadline: deterministic legal deadline computation for Singapore.

Public API:
    Calendar, load_calendar            working-day arithmetic over vendored holiday data
    Rule, Period, Direction, load_rules
    compute                            apply a Rule to a trigger date -> Result with trace
    limitation_period                  Limitation Act 1959 periods
    DeemedReceiptRule, deemed_receipt  contractual notice deemed-receipt arithmetic
"""

from .calendar import Calendar, HolidayDataMissingError, load_calendar
from .deemed_receipt import DeemedReceiptRule, deemed_receipt
from .engine import Result, compute
from .limitation import LimitationRule, limitation_period, load_limitation_rules
from .rules import Direction, Period, RollDirection, Rule, load_rules

__all__ = [
    "Calendar",
    "HolidayDataMissingError",
    "load_calendar",
    "Rule",
    "Period",
    "Direction",
    "RollDirection",
    "load_rules",
    "Result",
    "compute",
    "LimitationRule",
    "limitation_period",
    "load_limitation_rules",
    "DeemedReceiptRule",
    "deemed_receipt",
]

__version__ = "0.1.0"
