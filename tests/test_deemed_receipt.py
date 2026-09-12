from datetime import date, datetime, time

from sg_deadline import DeemedReceiptRule, deemed_receipt


def test_email_after_cutoff_next_business_day(cal):
    rule = DeemedReceiptRule(method="email", offset_days=1, business_days=True,
                             cutoff=time(17, 0))
    # Fri 13 Mar 18:00 -> treated as sent Mon 16 -> +1 bd -> Tue 17
    r = deemed_receipt(rule, datetime(2026, 3, 13, 18, 0), cal)
    assert r.deadline == date(2026, 3, 17)


def test_email_before_cutoff(cal):
    rule = DeemedReceiptRule(method="email", offset_days=1, business_days=True,
                             cutoff=time(17, 0))
    r = deemed_receipt(rule, datetime(2026, 3, 13, 10, 0), cal)
    assert r.deadline == date(2026, 3, 16)


def test_post_three_calendar_days_no_roll(cal):
    rule = DeemedReceiptRule(method="post", offset_days=3)
    r = deemed_receipt(rule, datetime(2026, 12, 24, 9, 0), cal)
    assert r.deadline == date(2026, 12, 27)  # Sunday; clause does not roll


def test_post_three_calendar_days_with_roll(cal):
    rule = DeemedReceiptRule(method="post", offset_days=3, roll_to_working_day=True)
    r = deemed_receipt(rule, datetime(2026, 12, 24, 9, 0), cal)
    assert r.deadline == date(2026, 12, 28)


def test_hand_delivery_on_holiday_defers(cal):
    rule = DeemedReceiptRule(method="hand", non_working_day_defers=True)
    r = deemed_receipt(rule, datetime(2026, 12, 25, 11, 0), cal)
    assert r.deadline == date(2026, 12, 28)


def test_verbatim_clause_appears_in_trace(cal):
    rule = DeemedReceiptRule(method="email", verbatim="deemed received when sent",
                             clause_ref="cl 21.3")
    r = deemed_receipt(rule, datetime(2026, 3, 13, 10, 0), cal)
    assert any("cl 21.3" in line for line in r.trace)
    assert any("deemed received when sent" in line for line in r.trace)
