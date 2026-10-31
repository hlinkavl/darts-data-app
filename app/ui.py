"""Shared look and helpers: colours (validated dataviz palette, dark variant), Plotly layout, formatting."""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Dark surface and text (dataviz reference palette, dark mode)
SURFACE = "#1a1a19"
TEXT = "#f0efec"
TEXT_2 = "#c3c2b7"
GRID = "#383835"
# Categorical slots in fixed order: blue, orange, aqua
SERIES = ["#3987e5", "#d95926", "#199e70"]
# Diverging pair: positive (helps) blue, negative (hurts) red, neutral gray
POSITIVE, NEGATIVE, NEUTRAL = "#3987e5", "#e66767", "#383835"
# Status palette, always shown with an icon and a label
STATUS = {"green": ("🟢", "OK", "#0ca30c"), "yellow": ("🟡", "Attention", "#fab219"), "red": ("🔴", "Problem", "#d03b3b")}

CREDITS = ("Data: Mastercaller / iDarts · Darts Orakel (until Oct 2026) · Wikipedia & Wikidata (CC BY-SA) · "
           "PDC Order of Merit. Non-commercial project.")


def layout(fig: go.Figure, height: int = 320, **kwargs) -> go.Figure:
    """Recessive grid and axes, one y-axis, hover on, dark surface."""
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=28, b=8), paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_2, size=13), hoverlabel=dict(bgcolor="#262624", font_color=TEXT, bordercolor=GRID),
        showlegend=False, **kwargs)
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, tickfont_color=TEXT_2)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, tickfont_color=TEXT_2)
    return fig


def strength(pi: float) -> float:
    """PI (0-10) back to strength (log-odds against the average top-32 player)."""
    p = min(max(pi / 10, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def head_to_head(pi_a: float, pi_b: float) -> float:
    """P(A beats B) in a typical match (first to 6 legs) from two PIs."""
    return 1 / (1 + math.exp(-(strength(pi_a) - strength(pi_b))))


# Same conversion as src/analytics/formats.py (kept in sync by tests/test_app_formats.py).
def _race(p: float, n: int) -> float:
    return sum(math.comb(n - 1 + k, k) * p ** n * (1 - p) ** k for k in range(n))


def match_probability(p_typical: float, first_to: int, unit: str = "legs") -> float:
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _race(mid, 6) < p_typical else (lo, mid)
    p_leg = (lo + hi) / 2
    return _race(p_leg, first_to) if unit == "legs" else _race(_race(p_leg, 3), first_to)


def pct(x, digits: int = 0) -> str:
    return "–" if x is None or pd.isna(x) else f"{100 * x:.{digits}f} %"


def num(x, digits: int = 1) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:.{digits}f}"


def oom_rank(log_rank_value) -> str:
    """The model stores the Order of Merit as -ln(rank)."""
    if log_rank_value is None or pd.isna(log_rank_value):
        return "–"
    rank = int(round(math.exp(-log_rank_value)))
    return "unranked" if rank >= 500 else f"#{rank}"


def status_label(status: str) -> str:
    icon, label, _ = STATUS.get(status, ("⚪", status, TEXT_2))
    return f"{icon} {label}"


def form_chips(results: list[str]) -> str:
    return " ".join("🟩" if r == "W" else "🟥" for r in results)


DISPLAY_NAMES = {
    "avg_l30": "3-Dart Average (L30)", "form": "Form (L10 vs L30)", "elo": "Opponent-Weighted Elo",
    "oom_rank": "PDC Order of Merit", "experience": "Experience", "big_stage_delta": "Big-Stage Delta",
    "stage_delta": "Stage Delta",
}


def predictor_name(code: str) -> str:
    return DISPLAY_NAMES.get(code, code.replace("_", " ").title())


def contributions_chart(row: pd.Series, predictors: list[str]) -> go.Figure:
    """Horizontal diverging bars: how each predictor moves the player's PI against the average top-32 player."""
    vals = [(predictor_name(p), float(row.get(f"contrib_{p}", np.nan))) for p in predictors]
    vals = [(n, v) for n, v in vals if not np.isnan(v)]
    vals.sort(key=lambda t: t[1])
    fig = go.Figure(go.Bar(
        x=[v for _, v in vals], y=[n for n, _ in vals], orientation="h",
        marker=dict(color=[POSITIVE if v >= 0 else NEGATIVE for _, v in vals], line=dict(color=SURFACE, width=2)),
        hovertemplate="%{y}: %{x:+.2f} log-odds<extra></extra>"))
    fig.add_vline(x=0, line_color=TEXT_2, line_width=1)
    return layout(fig, height=60 + 44 * len(vals), xaxis_title="effect on the win chance vs the average top-32 player (log-odds)")
