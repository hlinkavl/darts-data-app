"""Parse knockout draws from Wikipedia wikitext ({{#invoke:Bracket|NTeamBracket}} / {{NTeamBracket}} templates).

Supports draws of 2^n players without byes (World Championship since 2026: 8 sections of 16 + finals of 8;
other knockout majors in one or more blocks). Each round carries its format ("best of 7 sets" -> first to 4
sets) and, once played, the score, the 3-dart averages and the winner.
"""

import html
import re
import unicodedata
from dataclasses import dataclass, field

MIN_DRAW_SIZE = 16  # smaller brackets (e.g. only semi-finals and final) are not a tournament draw
BLOCK_START = re.compile(r"\{\{\s*(?:#invoke:\s*[Bb]racket\s*\|\s*)?(\d+)TeamBracket(-Byes)?\s*\|")
FORMAT = re.compile(r"best of (\d+) (sets|legs)", re.I)


@dataclass
class Match:
    slot: int                      # position within the round, 0-based, in draw order
    player_a: str | None
    player_b: str | None
    seed_a: str | None = None
    seed_b: str | None = None
    score_a: int | None = None
    score_b: int | None = None
    avg_a: float | None = None
    avg_b: float | None = None
    bold_a: bool = False           # Wikipedia marks the winner in bold (b=1), also for walkovers
    bold_b: bool = False
    walkover: bool = False         # advanced without playing: counts in the draw, not in backtests

    @property
    def winner(self) -> str | None:
        if self.score_a is not None and self.score_b is not None and self.score_a != self.score_b:
            return self.player_a if self.score_a > self.score_b else self.player_b
        if self.bold_a != self.bold_b:
            return self.player_a if self.bold_a else self.player_b
        return None


@dataclass
class Round:
    name: str
    first_to: int | None
    unit: str | None
    matches: list[Match] = field(default_factory=list)


@dataclass
class Draw:
    title: str
    rounds: list[Round]

    @property
    def players(self) -> list[str | None]:
        """First-round slots in draw order."""
        return [p for m in self.rounds[0].matches for p in (m.player_a, m.player_b)]


def _block_text(wikitext: str, start: int) -> str:
    """Text of the template starting at `start`, up to its matching closing braces."""
    depth, i = 0, start
    while i < len(wikitext) - 1:
        two = wikitext[i:i + 2]
        if two == "{{":
            depth += 1
            i += 2
        elif two == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return wikitext[start:i]
        else:
            i += 1
    return wikitext[start:]


def _params(block: str) -> dict[str, str]:
    """Top-level |key = value parameters of a template (nested templates kept intact)."""
    params, depth, key, buf = {}, 0, None, []
    body = block[2:-2]
    i = 0
    parts, current = [], []
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            current.append(two)
            i += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            current.append(two)
            i += 2
            continue
        if body[i] == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(body[i])
        i += 1
    parts.append("".join(current))
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip()
    return params


def _clean(text: str) -> str:
    text = re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"\{\{\s*nowrap\s*\|\s*(?:1=)?", "", text).replace("}}", "")
    text = html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ")  # &nbsp; marks an empty seed cell
    return re.sub(r"\s+", " ", text.replace("'''", "").replace("''", "")).strip()


def is_bold(value: str) -> bool:
    return bool(re.search(r"\|\s*b\s*=\s*1|'''", value or ""))


def parse_team(value: str) -> tuple[str | None, float | None]:
    """Player name and (if present) 3-dart average from a bracket team cell."""
    if not value or value.strip() in ("", "&nbsp;"):
        return None, None
    # {{#invoke:DartsRankings|PDCFlag|Name|avg=..}} or {{PDCFlag|Name|avg=..}}
    m = re.search(r"PDCFlag\s*\|\s*([^|}]+)(?:\|\s*avg\s*=\s*([\d.]*))?", value)
    if m:
        return m.group(1).strip(), float(m.group(2)) if m.group(2) else None
    avg = re.search(r"\(?\s*(\d{2,3}\.\d{1,2})\s*\)?", re.sub(r"\[\[[^\]]*\]\]", "", value))
    link = re.search(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", value)
    name = link.group(1) if link else _clean(re.sub(r"\{\{[^{}]*\}\}", "", value))
    name = re.sub(r"\s*\(darts player\)", "", name).strip()
    return (name or None), (float(avg.group(1)) if avg else None)


def _score(value: str | None) -> int | None:
    m = re.search(r"\d+", _clean(value or ""))
    return int(m.group()) if m else None


def parse_blocks(wikitext: str) -> list[dict]:
    """Every bracket template with its nearest heading, size and rounds."""
    blocks = []
    for m in BLOCK_START.finditer(wikitext):
        if m.group(2):  # -Byes brackets (96-player format, World Championship until 2025) are not supported yet
            blocks.append({"heading": "", "size": int(m.group(1)), "rounds": [], "byes": True})
            continue
        text = _block_text(wikitext, m.start())
        params = _params(text)
        size = int(m.group(1))
        # Rounds actually filled in: a section bracket may stop early (e.g. 16 players -> 2 qualifiers).
        n_rounds = max([r for r in range(1, size.bit_length())
                        if any(k.startswith(f"RD{r}-team") and v.strip() for k, v in params.items())] or [0])
        headings = re.findall(r"\n(={2,4})\s*([^=\n]+?)\s*\1", wikitext[:m.start()])
        rounds = []
        for r in range(1, n_rounds + 1):
            header = _clean(params.get(f"RD{r}", f"Round {r}"))
            fmt = FORMAT.search(header)
            name = re.split(r"\(best of|\d{1,2}[–-]\d{1,2} \w+|\d{1,2} \w+$", header)[0].strip() or f"Round {r}"
            rnd = Round(name=name, first_to=(int(fmt.group(1)) + 1) // 2 if fmt else None,
                        unit=fmt.group(2).lower() if fmt else None)
            n_matches = size >> r
            for k in range(n_matches):
                a, b = 2 * k + 1, 2 * k + 2

                def get(kind, idx):
                    return params.get(f"RD{r}-{kind}{idx:02d}", params.get(f"RD{r}-{kind}{idx}"))

                pa, avg_a = parse_team(get("team", a) or "")
                pb, avg_b = parse_team(get("team", b) or "")
                scores = (get("score", a) or "") + (get("score", b) or "")
                rnd.matches.append(Match(
                    slot=k, player_a=pa, player_b=pb,
                    seed_a=_clean(get("seed", a) or "") or None, seed_b=_clean(get("seed", b) or "") or None,
                    score_a=_score(get("score", a)), score_b=_score(get("score", b)), avg_a=avg_a, avg_b=avg_b,
                    bold_a=is_bold(get("team", a)), bold_b=is_bold(get("team", b)),
                    walkover="w/o" in scores.lower() or "walkover" in scores.lower(),
                ))
            rounds.append(rnd)
        blocks.append({"heading": headings[-1][1] if headings else "", "size": size, "rounds": rounds, "byes": False})
    return blocks


def build_draw(title: str, wikitext: str) -> Draw | None:
    """Combine section brackets and the finals bracket into one draw, or None if no supported draw exists.
    Empty first-round slots (byes) are kept as None; the other player goes through."""
    blocks = [b for b in parse_blocks(wikitext) if b["byes"] or b["rounds"]]
    if not blocks or any(b["byes"] for b in blocks):
        return None
    if len(blocks) == 1:
        draw = Draw(title, blocks[0]["rounds"])
        return draw if len(draw.players) >= MIN_DRAW_SIZE else None
    finals = [b for b in blocks if b["heading"].lower().startswith("final")]
    sections = [b for b in blocks if b not in finals]
    if len(finals) != 1 or not sections or len({(s["size"], len(s["rounds"])) for s in sections}) != 1:
        return None  # unexpected layout (e.g. a league); better no draw than a wrong one
    qualifiers = len(sections) * (sections[0]["size"] >> len(sections[0]["rounds"]))
    if qualifiers != finals[0]["size"]:
        return None
    rounds = []
    for r in range(len(sections[0]["rounds"])):
        first = sections[0]["rounds"][r]
        merged = Round(first.name, first.first_to, first.unit)
        for s in sections:
            merged.matches.extend(s["rounds"][r].matches)
        for k, match in enumerate(merged.matches):
            match.slot = k
        rounds.append(merged)
    return Draw(title, rounds + finals[0]["rounds"])


def normalize_name(name: str) -> str:
    """Lower-case ASCII name for matching Wikipedia names to Orakel names."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", ascii_name.lower()).strip()
