"""Titles won: every event winner in the results data, grouped for player profiles (data since 2021)."""

import pandas as pd

GROUPS = ["Major", "Players Championship", "European Tour", "World Series", "Other PDC TV event",
          "World Youth Championship", "Challenge / Development Tour"]


def title_group(category: str | None, tournament_name: str | None, is_major: bool) -> str | None:
    """Readable group of a won event, or None for events outside the PDC system (other organisations)."""
    if is_major:
        return "Major"
    if category in ("PT", "PC"):
        return "Players Championship"
    if category == "ET":
        return "European Tour"
    if category in ("WS", "WSD"):
        return "World Series"
    if category == "WYC":
        return "World Youth Championship"
    if tournament_name in ("Challenge Tour", "Development Tour"):
        return "Challenge / Development Tour"
    if category in ("U", "WC", "MJ", "PCF", "WGP"):
        return "Other PDC TV event"
    return None


def player_titles(events: pd.DataFrame) -> pd.DataFrame:
    """events: event_date, tournament_name, category, is_major, winner_key, winner_name."""
    e = events.dropna(subset=["winner_key"]).copy()
    e["title_group"] = [title_group(c, t, bool(m)) for c, t, m in zip(e["category"], e["tournament_name"], e["is_major"])]
    e = e.dropna(subset=["title_group"])
    e["event_date"] = pd.to_datetime(e["event_date"])
    out = e.rename(columns={"winner_key": "player_key", "winner_name": "player_name"})
    out["season"] = out["event_date"].dt.year
    cols = ["player_key", "player_name", "event_date", "season", "tournament_name", "title_group", "is_major"]
    return out[cols].drop_duplicates(["player_key", "event_date", "tournament_name"]).sort_values("event_date", ascending=False)
