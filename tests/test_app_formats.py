import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))
from analytics.formats import match_probability  # noqa: E402
import ui  # noqa: E402


def test_app_format_conversion_matches_analytics():
    for p in (0.3, 0.5, 0.715, 0.9):
        for n, unit in ((3, "legs"), (6, "legs"), (10, "legs"), (3, "sets"), (7, "sets")):
            assert np.isclose(ui.match_probability(p, n, unit), match_probability(p, n, unit), atol=1e-9)


def test_head_to_head_from_pi():
    assert np.isclose(ui.head_to_head(7.35, 4.10), 0.80, atol=0.005)
    assert np.isclose(ui.head_to_head(5.0, 5.0), 0.5)
