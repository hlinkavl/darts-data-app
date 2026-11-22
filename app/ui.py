"""Shared look and helpers: colours (validated dataviz palette, dark variant), Plotly layout, formatting."""

import math

import pandas as pd
import plotly.graph_objects as go

# Dark surface and text (dataviz reference palette, dark mode)
SURFACE = "#1a1a19"
TEXT = "#f0efec"
TEXT_2 = "#c3c2b7"
GRID = "#383835"
# Categorical slots in fixed order: blue, orange, aqua
SERIES = ["#3987e5", "#d95926", "#199e70"]
# Diverging pair: positive (helps) blue, negative (hurts) red
POSITIVE, NEGATIVE = "#3987e5", "#e66767"
# Status palette, always shown with an icon and a label
STATUS = {"green": ("🟢", "OK", "#0ca30c"), "yellow": ("🟡", "Attention", "#fab219"), "red": ("🔴", "Problem", "#d03b3b")}

# Overall health as a pill: label, background, text colour (Data & Health page and the sidebar)
HEADLINE = {"green": ("All checks passed", "#2a3a2a", "#8fd18f"), "yellow": ("Needs attention", "#3d3420", "#f2c46b"),
            "red": ("Problem", "#4a2323", "#ff8a8a")}

CREDITS = ("Data: Wikipedia & Wikidata (CC BY-SA) · PDC Order of Merit · history: Darts Orakel (until Oct 2026), "
           "Mastercaller / iDarts (until Nov 2026). Non-commercial project.")


def layout(fig: go.Figure, height: int = 320, **kwargs) -> go.Figure:
    """Recessive grid and axes, one y-axis, hover on, no zoom, dark surface."""
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=28, b=8), paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_2, size=13), hoverlabel=dict(bgcolor="#262624", font_color=TEXT, bordercolor=GRID),
        showlegend=False, dragmode=False, **kwargs)  # no drag-zoom: on a phone a drag must scroll the page
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
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


def signed(x, digits: int = 2) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:+.{digits}f}"


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
    "stage_delta": "Stage Delta", "avg_major": "3-Dart Average on Majors (L20)", "form_major": "Form on Majors",
    "major_elo": "Big-Stage Elo", "major_experience": "Big-Stage Experience",
    "oom_momentum": "Order of Merit Momentum", "major_qf_12m": "Major Quarter-finals (12 months)",
    "major_points_12m": "Major Results Points", "major_titles_24m": "Major Titles (24 months)",
    "top32_share_5y": "Time in the Top 32", "oom_best_3y": "Best Order of Merit Rank (3 years)",
}


def predictor_name(code: str) -> str:
    return DISPLAY_NAMES.get(code, code.replace("_", " ").title())


# ------------------------------------------------------------------------------------------- help texts

PI_HELP = ("Performance Index: 10 × the chance to beat an average top-32 player in a typical match (first to 6 legs). "
           "5 = a typical top-32 player, 7 = wins 70 % of such matches.")
EFFECTIVE_AVERAGE_HELP = (
    "The player's whole strength as one 3-dart average. Start from an average top-32 player (the mean of the 32 "
    "strongest players): their 3-dart average is the base. Compare the player with them in every input of the model "
    "(3-dart average, form, Elo, Order of Merit) and turn each gap into average points. Base + gaps = Effective "
    "Average, and the PI follows from it. Read it like a normal average: 102 beats 97.")


# ----------------------------------------------------------------------------------------------- photos

def photo_url(image_file, width: int = 240) -> str | None:
    """Wikimedia Commons thumbnail of the player's photo (free licence), or None."""
    from urllib.parse import quote

    if not isinstance(image_file, str) or not image_file:
        return None
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(image_file.replace(' ', '_'))}?width={width}"


def photo_credit(image_file) -> str:
    from urllib.parse import quote

    return f"[Photo: Wikimedia Commons](https://commons.wikimedia.org/wiki/File:{quote(image_file.replace(' ', '_'))})"


def initials(name) -> str:
    parts = [p for p in str(name or "").replace("-", " ").split() if p[:1].isalpha()]
    return ((parts[0][0] + parts[-1][0]) if len(parts) > 1 else (parts[0][:2] if parts else "?")).upper()


def avatar(image_file, size: int = 34, name=None, ring: str | None = None) -> str:
    """Round photo as inline HTML; players without a free photo get their initials (empty without a name)."""
    url = photo_url(image_file, 2 * size)
    border = f"border:2px solid {ring};" if ring else ""
    base = (f"width:{size}px;height:{size}px;border-radius:50%;vertical-align:middle;margin:0 6px;flex:none;{border}")
    if url:
        return f"<img src='{url}' alt='' style='{base}object-fit:cover;object-position:top'>"
    if not name:
        return ""
    return (f"<span style='{base}display:inline-flex;align-items:center;justify-content:center;background:{GRID};"
            f"color:{TEXT_2};font-weight:600;font-size:{max(10, int(size * 0.38))}px'>{initials(name)}</span>")


def name_key(name) -> str:
    """Accent-, case- and punctuation-insensitive key, to match names between Wikipedia and the results data."""
    import re
    import unicodedata

    if not isinstance(name, str):
        return ""
    special = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss"})
    key = unicodedata.normalize("NFKD", name.translate(special)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"([aou])e", r"\1", " ".join(re.sub(r"[^a-z ]", "", key).split()))


def surnames(names) -> dict[str, str]:
    """Short names for a bracket: everything after the first name ('van Gerwen'); initial added when two players
    share a surname ('R. Smith', 'M. Smith')."""
    names = [n for n in dict.fromkeys(names) if isinstance(n, str) and n]
    short = {n: (n.split(" ", 1)[1] if " " in n else n) for n in names}
    counts = pd.Series(list(short.values())).value_counts()
    return {n: (f"{n[0]}. {s}" if counts[s] > 1 else s) for n, s in short.items()}


# ------------------------------------------------------------------------------------------ blocks

WIN, LOSS = STATUS["green"][2], STATUS["red"][2]


# ------------------------------------------------------------------------------------------- page styles

# Shared CSS: the sidebar card, the cards built from HTML, and the phone layout (most visitors open the public link
# on a phone). Classes are used where a phone needs a different layout than inline styles allow.
CSS = f"""
<style>
.side-card {{border:1px solid {GRID};border-radius:12px;padding:14px 16px;background:#20201f}}
.side-card .brand {{font-weight:700;color:{TEXT};font-size:1.02em;margin-bottom:10px}}
.side-card .pill {{display:inline-block;border-radius:999px;padding:3px 12px;font-size:0.8em;font-weight:600}}
.side-card .kv {{display:flex;justify-content:space-between;gap:10px;font-size:0.85em;padding:7px 0;
                 border-top:1px solid {GRID}}}
.side-card .kv span {{color:{TEXT_2}}}
.side-card .kv b {{color:{TEXT};font-weight:600;text-align:right}}
.side-card .note {{color:{TEXT_2};font-size:0.78em;margin-top:8px;line-height:1.45}}
.side-credits {{color:{TEXT_2};font-size:0.72em;line-height:1.5;margin-top:14px;opacity:0.85}}
.st-key-mobile_nav_row, .st-key-mobile_status {{display:none}}
.mc-grid {{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px;margin-bottom:8px}}
.mc-grid-2 {{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:8px}}
.mc-row {{display:flex;align-items:center;gap:6px;padding:3px 0;font-size:0.92em}}
.mc-row img, .mc-row > span:first-child {{margin:0 !important}}
.mc-name {{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.vs-side {{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;text-align:center;gap:4px}}
.vs-side .nm {{line-height:1.25}}
.vs-centre {{min-width:84px;text-align:center}}
@media (max-width: 640px) {{
  .st-key-mobile_nav_row {{display:block;margin-bottom:-0.4rem}}
  .st-key-mobile_status {{display:block}}
  [data-testid="stSidebar"], [data-testid="stExpandSidebarButton"] {{display:none !important}}
  .st-key-mobile_nav_row [data-testid="stButtonGroup"] > div {{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;
                                                              padding-bottom:2px}}
  .st-key-mobile_nav_row [data-testid="stButtonGroup"] button {{flex:0 0 auto;max-width:none}}
  .st-key-mobile_nav_row [data-testid="stButtonGroup"] button * {{white-space:nowrap;overflow:visible;
                                                                 text-overflow:clip}}
  [data-testid="stMainBlockContainer"] {{padding-left:0.9rem;padding-right:0.9rem;padding-top:3.2rem}}
  [data-testid="stMainBlockContainer"] h1 {{font-size:1.7rem}}
  [data-testid="stMainBlockContainer"] h2 {{font-size:1.3rem}}
  [data-testid="stMainBlockContainer"] h3 {{font-size:1.15rem}}
  .vs-centre {{min-width:58px}}
  .br-early {{display:none !important}}
  .mc-grid, .mc-grid-2 {{grid-template-columns:1fr}}
  .ph-card {{padding:14px !important}}
  .ph-photo img, .ph-photo > span {{width:76px !important;height:76px !important}}
  .ph-name {{flex:1 1 0 !important;min-width:0 !important;padding-right:0 !important}}
  .ph-name .big {{font-size:1.5em !important}}
  .ph-metrics {{flex:1 1 100% !important;border-top:1px solid {GRID};padding-top:12px}}
  .ph-metric {{flex:1 1 0 !important;min-width:0 !important;padding:0 6px !important}}
  .ph-metric:first-child {{border-left:none !important}}
  .ph-metric .val {{font-size:2em !important}}
  .bd-table {{font-size:0.9em}}
  .h2h-side img, .h2h-side > span:first-child {{width:60px !important;height:60px !important}}
  .h2h-side .chance {{font-size:2em !important}}
}}
</style>
"""


def status_line(status: dict) -> str:
    """One line for the phone: health and when the data was refreshed (the details open below it)."""
    icon, _, _ = STATUS.get(status["status"], ("⚪", "", ""))
    label = HEADLINE.get(status["status"], HEADLINE["green"])[0]
    when = status["checked_at"]
    return f"{icon} {label}" + (f" · updated {pd.Timestamp(when):%d %b, %H:%M} UTC" if when is not None and pd.notna(when) else "")


def sidebar_status(status: dict) -> str:
    """The sidebar card: health as a pill, then when the data ends and when it was refreshed."""
    label, bg, fg = HEADLINE.get(status["status"], HEADLINE["green"])

    def when(ts, fmt):
        return f"{pd.Timestamp(ts):{fmt}}" if ts is not None and pd.notna(ts) else "–"

    rows = [("Results until", when(status["data_until"], "%d %b %Y")),
            ("Updated", when(status["checked_at"], "%d %b, %H:%M") + (" UTC" if status["checked_at"] is not None else "")),
            ("Model", status["model_version"] or "–")]
    note = {"public": "Public copy, refreshed every night during majors.",
            "local": "🧪 Local snapshot (development)."}.get(status["mode"], "")
    return (f"<div class='side-card'><div class='brand'>🎯 Darts Performance Analyzer</div>"
            + "".join(f"<div class='kv'><span>{k}</span><b>{v}</b></div>" for k, v in rows)
            + (f"<div class='note'>{note}</div>" if note else "")
            + f"<div style='text-align:center;margin-top:12px'>"
            f"<span class='pill' style='background:{bg};color:{fg}'>● {label}</span></div>"
            f"</div><div class='side-credits'>{CREDITS}</div>")
