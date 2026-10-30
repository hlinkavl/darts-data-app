"""Chronological order of matches within a day.

Match ids do not follow the order of play: Darts Orakel numbers single-day Players Championship events
backwards (the final has the lowest id). Ordering by id would let a first-round match "see" the same player's
later rounds that day, which only exist if he won, so every point-in-time feature must order by round first.
"""

import re

import numpy as np
import pandas as pd

EARLIEST = 4096  # groups, round robin and unknown round names count as early


def players_left(round_name: str | None) -> int:
    """Players still in the event at this round (Last 64 -> 64, Quarter-final -> 8, Final -> 2); larger = earlier."""
    name = round_name.lower() if isinstance(round_name, str) else ""
    if m := re.search(r"last\s*(\d+)", name):
        return int(m.group(1))
    if "quarter" in name:
        return 8
    if "semi" in name:
        return 4
    if re.search(r"\bfinal\b", name):
        return 2
    if m := re.search(r"(?:round|rd)\s*(\d+)|(first|second|third|fourth|fifth) round", name):
        n = int(m.group(1)) if m.group(1) else ["first", "second", "third", "fourth", "fifth"].index(m.group(2)) + 1
        return EARLIEST // 2 ** n
    return EARLIEST


def order_key(df: pd.DataFrame) -> pd.Series:
    """Sort key within a day: earlier rounds first (more players left)."""
    if "round" not in df.columns:
        return pd.Series(np.zeros(len(df)), index=df.index)
    return -df["round"].map(players_left).astype(float)
