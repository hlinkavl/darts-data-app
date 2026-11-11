"""AI form summaries for player profiles: the prompt built from a player's numbers and PDC news, and which players
need a new summary.

The model only rewrites facts it is given (no own knowledge, no predictions beyond the PI), and a summary is
generated again only when its inputs change, because every call costs Databricks compute.
"""

import hashlib

import pandas as pd

NEWS_DAYS = 60          # news older than this is not used
NEWS_PER_PLAYER = 3
TOP_N = 32              # summaries for the PI top 32, plus every tracked player with recent news
MAX_PER_RUN = 60        # cap per refresh (candidates: PI top 32 + players with news, ~40); only changed inputs are regenerated

INSTRUCTIONS = """You write a short form summary for a darts player's profile page.
Use only the facts below. Do not add results, titles, ages, nicknames or opinions that are not in the facts.
Write 2 or 3 sentences in English, neutral and factual, at most 70 words. No betting advice.
Mention the most important recent result or news first, then the current form in numbers.
Explain the Performance Index only as "PI", never define it."""


def _fmt(x, digits: int = 1, sign: bool = False) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    return f"{x:+.{digits}f}" if sign else f"{x:.{digits}f}"


def prompt(player: pd.Series, recent: pd.DataFrame, news: pd.DataFrame) -> str:
    """player: player_name, rank, pi, avg_l30, form, effective_average, oom (official rank or NaN).
    recent: the last matches (match_date, tournament_name, round, opponent_name, result, score, average).
    news: relevant articles (published, title, snippet), newest first."""
    lines = [INSTRUCTIONS, "", f"Player: {player['player_name']}",
             f"PDC Order of Merit: #{int(player['oom'])}" if pd.notna(player.get("oom")) else "PDC Order of Merit: unranked",
             f"PI: {_fmt(player['pi'], 2)} (#{int(player['rank'])} of tracked players; 5 = an average top-32 player)",
             f"3-dart average, last 30 matches: {_fmt(player['avg_l30'], 2)}",
             f"Form (average of last 10 minus last 30): {_fmt(player['form'], 2, sign=True)}",
             "", "Last matches (newest first):"]
    for m in recent.itertuples():
        avg = f", average {_fmt(m.average, 2)}" if pd.notna(m.average) else ""
        lines.append(f"- {pd.Timestamp(m.match_date):%d %b %Y}, {m.tournament_name}, {m.round}: "
                     f"{'won' if m.result == 'W' else 'lost'} {m.score} against {m.opponent_name}{avg}")
    if len(news):
        lines += ["", "PDC news (newest first):"]
        for n in news.itertuples():
            lines.append(f"- {pd.Timestamp(n.published):%d %b %Y}, \"{n.title}\": {n.snippet}")
    return "\n".join(lines)


def input_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def candidates(current: pd.DataFrame, news: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    """Players to summarise: the PI top TOP_N and anyone with relevant news in the last NEWS_DAYS days."""
    recent_news = news[news["relevant"] & (pd.to_datetime(news["published"], utc=True)
                                            >= today.tz_localize("UTC") - pd.Timedelta(days=NEWS_DAYS))]
    keys = set(current.nsmallest(TOP_N, "rank")["player_key"]) | set(recent_news["player_key"])
    return current[current["player_key"].isin(keys)].sort_values("rank")


def build_prompts(current: pd.DataFrame, recent_matches: pd.DataFrame, news: pd.DataFrame,
                  today: pd.Timestamp) -> pd.DataFrame:
    """player_key, player_name, prompt, input_hash, news_links for every candidate."""
    rows = []
    usable = news[news["relevant"]].copy()
    usable["published"] = pd.to_datetime(usable["published"], utc=True)
    usable = usable[usable["published"] >= today.tz_localize("UTC") - pd.Timedelta(days=NEWS_DAYS)]
    for p in candidates(current, news, today).itertuples():
        row = pd.Series(p._asdict())
        mine = usable[usable["player_key"] == p.player_key].sort_values("published", ascending=False).head(NEWS_PER_PLAYER)
        last = recent_matches[recent_matches["player_key"] == p.player_key].sort_values("recency").head(5)
        text = prompt(row, last, mine)
        rows.append({"player_key": p.player_key, "player_name": p.player_name, "prompt": text,
                     "input_hash": input_hash(text), "news_links": list(mine["link"])})
    return pd.DataFrame(rows, columns=["player_key", "player_name", "prompt", "input_hash", "news_links"])


def to_generate(prompts: pd.DataFrame, existing: pd.DataFrame | None, model: str) -> pd.DataFrame:
    """Prompts whose summary is missing, failed, or was made from other inputs or by another model; at most
    MAX_PER_RUN, best-ranked first (prompts come sorted by PI rank)."""
    if existing is None or existing.empty:
        return prompts.head(MAX_PER_RUN)
    ok = existing[existing["narrative"].notna() & (existing["model"] == model)]
    done = set(zip(ok["player_key"], ok["input_hash"]))
    todo = prompts[[(k, h) not in done for k, h in zip(prompts["player_key"], prompts["input_hash"])]]
    return todo.head(MAX_PER_RUN)
