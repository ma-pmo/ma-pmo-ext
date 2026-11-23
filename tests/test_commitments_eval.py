"""Roadmap 9, step 6: the commitment evaluation's criteria hold on a few cases."""
from __future__ import annotations

from ma_pmo.eval import commitments as ce


def test_conditions_are_noticed_when_missed_and_left_alone_when_kept():
    kept = ce.condition_case("on_time", 3)
    absent = ce.condition_case("absent", 3)
    assert len(kept) == len(absent) == 4  # two gates, a gate and an approval condition each
    assert all(r["kept"] and not r["kept_marked_missed"] and r["days_to_resolve"] == 2
               for r in kept)
    assert all(not r["missed_unnoticed"] and not r["missed_not_escalated"]
               and not r["missed_not_reopened"] for r in absent)


def test_questions_use_answers_on_time_and_mark_defaults():
    on_time, absent = ce.question_case("on_time", 1), ce.question_case("absent", 1)
    assert on_time["asked"] == 1 and not on_time["default_used"] and on_time["run"] == "succeeded"
    assert absent["default_used"] and absent["unmarked_defaults"] == 0
    assert ce.question_case(None, 1)["needless_questions"] == 0
