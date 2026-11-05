"""PDC news per player: which tracked players an article is about, and the sentences that mention them.

Matching is on the full name (accent- and case-insensitive), so "Smith" alone never assigns an article to one of
several Smiths. Once the full name appears, later sentences with just the surname count too, unless another
mentioned player shares that surname.
"""

import re
import unicodedata

import pandas as pd

SPECIAL_LETTERS = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss"})
SNIPPET_SENTENCES = 3
MAX_SENTENCE_CHARS = 400   # longer "sentences" are lists (entries, draws, rankings), not about anyone
FEATURE_MAX_PLAYERS = 8    # an article naming more players is a round-up: relevant only to players in its title


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").translate(SPECIAL_LETTERS)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join((text or "").split())) if s.strip()]


def _contains(haystack: str, needle: str) -> bool:
    return bool(needle) and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def player_mentions(articles: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """articles: link, title, published, text. players: player_key, player_name (tracked players).
    Returns one row per (article, player): player_key, player_name, link, title, published, snippet,
    in_title (the player is in the headline), players_in_article and relevant (headline, or an article about a few
    players); round-ups such as entry lists are kept but not relevant."""
    names = [(k, n, norm(n)) for k, n in zip(players["player_key"], players["player_name"]) if norm(n)]
    rows = []
    for a in articles.drop_duplicates("link").itertuples():
        body = f"{a.title}. {a.text or ''}"
        flat = norm(body)
        found = [(k, n, key) for k, n, key in names if _contains(flat, key)]
        surnames = pd.Series([key.split()[-1] for _, _, key in found]).value_counts()
        title = norm(a.title)
        for k, n, key in found:
            surname = key.split()[-1]
            unique_surname = surnames.get(surname, 0) == 1
            mentions = lambda t: _contains(t, key) or (unique_surname and _contains(t, surname))
            picked = [s for s in _sentences(a.text) if len(s) <= MAX_SENTENCE_CHARS and mentions(norm(s))]
            in_title = mentions(title)
            rows.append({"player_key": k, "player_name": n, "link": a.link, "title": a.title,
                         "published": pd.to_datetime(a.published, utc=True), "snippet": " ".join(picked[:SNIPPET_SENTENCES]),
                         "in_title": in_title, "players_in_article": len(found),
                         "relevant": bool(in_title or (len(found) <= FEATURE_MAX_PLAYERS and picked))})
    cols = ["player_key", "player_name", "link", "title", "published", "snippet", "in_title", "players_in_article",
            "relevant"]
    return pd.DataFrame(rows, columns=cols).sort_values(["player_key", "published"], ascending=[True, False],
                                                        ignore_index=True)
