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


# ------------------------------------------------------------------------------------------- help texts

PI_HELP = ("Performance Index: 10 × the chance to beat an average top-32 player in a typical match (first to 6 legs). "
           "5 = a typical top-32 player, 7 = wins 70 % of such matches.")
EFFECTIVE_AVERAGE_HELP = (
    "The player's whole strength translated into 3-dart-average points. It starts from his real average over the "
    "last 30 matches and adds (or takes away) what the model sees on top of it: the quality of the opponents he "
    "beats (Elo), his current form and his Order of Merit ranking, each converted into average points. "
    "Read it like a normal average: 102 beats 97.")


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


def info_block(rows: list[tuple[str, str]], note: str | None = None) -> str:
    """Key facts as tiles: the value on top, a short label under it (HTML); wraps to more rows on narrow screens."""
    cells = "".join(f"<div style='padding:2px 0'><div style='color:{TEXT};font-size:1.15em;font-weight:600'>"
                    f"{value}</div><div style='color:{TEXT_2};font-size:0.8em;line-height:1.3;"
                    f"margin-top:2px'>{label}</div></div>"
                    for label, value in rows)
    foot = (f"<div style='color:{TEXT_2};font-size:0.85em;margin-top:12px;padding-top:10px;border-top:1px solid {GRID}'>"
            f"{note}</div>") if note else ""
    return (f"<div style='border:1px solid {GRID};border-radius:10px;padding:14px 18px;margin:4px 0 16px'>"
            f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px 22px;"
            f"align-items:start'>{cells}</div>{foot}</div>")
