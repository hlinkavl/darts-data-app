import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analytics import registry  # noqa: E402

ACTIVE = pd.DataFrame({"predictor": ["avg_l30", "elo", "form"], "weight_pct": [58.0, 21.0, 21.0]})


def test_first_version_is_promoted():
    assert registry.decide(ACTIVE, 0.64, None, None).promote


def test_changed_predictors_need_review():
    cand = pd.DataFrame({"predictor": ["avg_l30", "elo", "form", "big_stage_delta"], "weight_pct": [55, 20, 20, 5]})
    d = registry.decide(cand, 0.63, ACTIVE, 0.64)
    assert not d.promote and "big_stage_delta" in d.reason


def test_worse_log_loss_is_rejected_and_small_change_promoted():
    worse = registry.decide(ACTIVE, 0.650, ACTIVE, 0.640)
    assert not worse.promote and "worse" in worse.reason
    assert registry.decide(ACTIVE.assign(weight_pct=[60.0, 20.0, 20.0]), 0.641, ACTIVE, 0.640).promote


def test_large_weight_shift_needs_review():
    cand = ACTIVE.assign(weight_pct=[38.0, 41.0, 21.0])
    d = registry.decide(cand, 0.630, ACTIVE, 0.640)
    assert not d.promote and "moved" in d.reason
