"""Model promotion policy: every refit creates a candidate; only a safe candidate replaces the active model.

Rules (docs/PERFORMANCE_INDEX.md, "Model versions"):
1. No active model yet: the candidate becomes active.
2. The selected predictors changed: the candidate is NOT activated. A change in what the index is made of is
   a methodology change and needs a human decision (the health report flags it).
3. Same predictors: the candidate becomes active if its test log loss is not worse than the active model's
   by more than LOG_LOSS_TOLERANCE, and no predictor's share of the index moved by more than WEIGHT_SHIFT_LIMIT
   percentage points. Otherwise the active model stays and the health report says why.
"""

from dataclasses import dataclass

import pandas as pd

LOG_LOSS_TOLERANCE = 0.005
WEIGHT_SHIFT_LIMIT = 15.0  # percentage points of "share of the index"


@dataclass
class Decision:
    promote: bool
    reason: str


def decide(candidate: pd.DataFrame, candidate_test_log_loss: float,
           active: pd.DataFrame | None, active_test_log_loss: float | None) -> Decision:
    """candidate / active: coefficient tables (predictor, weight_pct)."""
    if active is None or active.empty:
        return Decision(True, "first model version")
    new, old = set(candidate["predictor"]), set(active["predictor"])
    if new != old:
        added, removed = sorted(new - old), sorted(old - new)
        return Decision(False, f"selected predictors changed (added {added or 'none'}, removed {removed or 'none'}): "
                               "needs review before it can replace the active model")
    if active_test_log_loss is not None and candidate_test_log_loss > active_test_log_loss + LOG_LOSS_TOLERANCE:
        return Decision(False, f"test log loss worse: {candidate_test_log_loss:.4f} vs active {active_test_log_loss:.4f}")
    shift = (candidate.set_index("predictor")["weight_pct"] - active.set_index("predictor")["weight_pct"]).abs()
    if shift.max() > WEIGHT_SHIFT_LIMIT:
        return Decision(False, f"weight of {shift.idxmax()} moved by {shift.max():.1f} percentage points "
                               f"(limit {WEIGHT_SHIFT_LIMIT:.0f}): needs review")
    return Decision(True, f"same predictors, test log loss {candidate_test_log_loss:.4f}"
                          + (f" (active {active_test_log_loss:.4f})" if active_test_log_loss is not None else "")
                          + f", largest weight shift {shift.max():.1f} pp")
