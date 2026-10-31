"""Wikipedia / Wikidata: tournament pages (draws, results) and player background. Content is CC BY-SA."""

import re
import unicodedata
from datetime import date

from .http import PoliteClient

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# Wikidata properties used for player background.
PROPS = {"P569": "date_of_birth", "P27": "citizenship", "P1449": "nickname", "P18": "image"}


def fetch_page_wikitext(client: PoliteClient, title: str) -> dict:
    """Raw wikitext of a page (e.g. '2026 PDC World Darts Championship'); draws are parsed downstream."""
    data = client.get_json(
        WIKI_API,
        {"action": "parse", "page": title, "prop": "wikitext|revid", "format": "json", "redirects": 1},
    )
    if "error" in data:
        return {"title": title, "error": data["error"].get("info")}
    parse = data["parse"]
    return {"title": parse["title"], "revid": parse["revid"], "wikitext": parse["wikitext"]["*"]}


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
DARTS_PLAYER = "Q18574233"  # occupation (P106): darts player
DARTS = "Q131471"           # sport (P641): darts
# Bumped when matching improves, so earlier records are fetched again once.
MATCHER_VERSION = 2
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png")


# Letters that Unicode does not decompose into a base letter plus an accent.
SPECIAL_LETTERS = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss", "æ": "ae", "ı": "i"})


def name_key(name: str) -> str:
    """Accent- and case-insensitive key; 'ue'/'oe'/'ae' fold to the plain vowel (Grüllich = Gruellich)."""
    key = unicodedata.normalize("NFKD", name.translate(SPECIAL_LETTERS)).encode("ascii", "ignore").decode().lower()
    key = re.sub(r"[^a-z ]", "", key)
    return re.sub(r"([aou])e", r"\1", " ".join(key.split()))


def _searches(client: PoliteClient, name: str):
    """Candidate Wikidata items, one search strategy at a time. Searching only among items whose occupation is
    darts player (or sport is darts) finds common names (Peter Wright, Michael Smith) that a plain label search
    buries under namesakes; the plain search catches items with neither statement."""
    for statement in (f"P106={DARTS_PLAYER}", f"P641={DARTS}"):
        hits = client.get_json(
            WIKIDATA_API,
            {"action": "query", "list": "search", "srsearch": f"{name} haswbstatement:{statement}", "srlimit": 5,
             "format": "json"},
        ).get("query", {}).get("search", [])
        yield [h["title"] for h in hits]
    hits = client.get_json(
        WIKIDATA_API,
        {"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 7, "format": "json"},
    ).get("search", [])
    yield [h["id"] for h in hits if "dart" in h.get("description", "").lower()]


def _pick(entities: dict, candidates: list[str], name: str) -> str | None:
    """The first candidate whose label or alias (any language) is the player's name. A single candidate whose
    label shares the surname is accepted too (spelling variants)."""
    key = name_key(name)
    found = [q for q in candidates if q in entities]
    for qid in found:
        e = entities[qid]
        names = [v["value"] for v in e.get("labels", {}).values()]
        names += [a["value"] for aliases in e.get("aliases", {}).values() for a in aliases]
        if key in {name_key(n) for n in names}:
            return qid
    if len(found) == 1:
        label = name_key(entities[found[0]].get("labels", {}).get("en", {}).get("value", ""))
        if key.split()[-1:] == label.split()[-1:]:
            return found[0]
    return None


def _commons_photo(client: PoliteClient, category: str, name: str) -> str | None:
    """A photo from the player's Wikimedia Commons category; files naming the player are preferred."""
    members = client.get_json(
        COMMONS_API,
        {"action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}", "cmtype": "file",
         "cmlimit": 50, "format": "json"},
    ).get("query", {}).get("categorymembers", [])
    files = [m["title"].removeprefix("File:") for m in members if m["title"].lower().endswith(PHOTO_EXTENSIONS)]
    surname = name_key(name).split()[-1] if name_key(name) else ""
    named = [f for f in files if surname and surname in name_key(f)]
    return (named or files or [None])[0]


def fetch_player_background(client: PoliteClient, name: str) -> dict:
    """Date of birth, citizenship, nickname, image and English Wikipedia intro for one player.

    The photo comes from Wikidata (P18); if there is none, from the free lead image of the English Wikipedia
    article; if there is none, from the player's Wikimedia Commons category. All three are freely licensed."""
    record = {"name": name, "wikidata_id": None, "matcher": MATCHER_VERSION, "fetched_on": date.today().isoformat()}
    qid, entity, tried = None, None, set()
    for candidates in _searches(client, name):
        candidates = [q for q in candidates if q not in tried]
        if not candidates:
            continue
        tried |= set(candidates)
        entities = client.get_json(
            WIKIDATA_API,
            {"action": "wbgetentities", "ids": "|".join(candidates),
             "props": "labels|aliases|claims|sitelinks|descriptions", "format": "json"},
        ).get("entities", {})
        qid = _pick(entities, candidates, name)
        if qid:
            entity = entities[qid]
            break
    if qid is None:
        return record

    record |= {"wikidata_id": qid, "description": entity.get("descriptions", {}).get("en", {}).get("value")}
    for pid, field in PROPS.items():
        values = []
        for claim in entity.get("claims", {}).get(pid, []):
            value = claim["mainsnak"].get("datavalue", {}).get("value")
            if isinstance(value, dict):
                value = value.get("time") or value.get("id") or value.get("text")
            if value:
                values.append(value)
        record[field] = values

    record["image_source"] = "wikidata" if record["image"] else None

    wiki_title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
    record["enwiki_title"] = wiki_title
    if wiki_title:
        extract = client.get_json(
            WIKI_API,
            {"action": "query", "prop": "extracts|pageimages", "exintro": 1, "explaintext": 1, "piprop": "name",
             "pilicense": "free", "titles": wiki_title, "format": "json", "redirects": 1},
        )
        page = next(iter(extract.get("query", {}).get("pages", {}).values()), {})
        record["intro"] = page.get("extract")
        if not record["image"] and page.get("pageimage"):
            record["image"], record["image_source"] = [page["pageimage"]], "wikipedia"

    category = next((c["mainsnak"].get("datavalue", {}).get("value") for c in entity.get("claims", {}).get("P373", [])), None)
    if not record["image"] and category:
        photo = _commons_photo(client, category, name)
        if photo:
            record["image"], record["image_source"] = [photo], "commons"
    return record


def draw_players(wikitext: str) -> set[str]:
    """Player names in a tournament page's draw templates ({{PDCFlag|Name|..}})."""
    return {m.strip() for m in re.findall(r"PDCFlag\s*\|\s*([^|}]+)", wikitext or "") if m.strip()}


def needs_background(previous: dict | None, today: date, retry_days: int = 30) -> bool:
    """Fetch when the player is new or was matched by an older matcher; retry players without a photo monthly."""
    if previous is None or previous.get("matcher", 1) < MATCHER_VERSION:
        return True
    if previous.get("image"):
        return False
    fetched = date.fromisoformat(previous.get("fetched_on", "2000-01-01"))
    return (today - fetched).days >= retry_days


RANKINGS_MODULE = "Module:DartsRankings/data/PDC Rankings"
RANKING_ROW = re.compile(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*"£\s*([\d,]+)"\s*\}')
RANKINGS_PARSER = 2  # 1 also read the module's previous table (data.rankingsold), giving duplicate players


def current_table(module_text: str) -> str:
    """Only `data.rankings = {...}`; the module also keeps the previous update as `data.rankingsold`."""
    start = re.search(r"data\.rankings\s*=\s*\{", module_text)
    if not start:
        return module_text
    end = module_text.find("data.", start.end())
    return module_text[start.end(): end if end != -1 else None]


def fetch_rankings_at(client: PoliteClient, as_of: str) -> list[dict]:
    """Official PDC Order of Merit as it stood on a date (YYYY-MM-DD), from the Wikipedia data module that
    darts articles use for rankings (source: PDC/PDPA). The module is updated after every ranking event."""
    data = client.get_json(WIKI_API, {
        "action": "query", "prop": "revisions", "titles": RANKINGS_MODULE, "rvlimit": 1, "rvdir": "older",
        "rvstart": f"{as_of}T23:59:59Z", "rvprop": "ids|timestamp|content", "rvslots": "main", "format": "json",
    })
    page = next(iter(data["query"]["pages"].values()))
    if not page.get("revisions"):
        return []
    rev = page["revisions"][0]
    return [{"as_of": as_of, "revision_id": rev["revid"], "revision_time": rev["timestamp"], "player_name": name,
             "rank": int(rank), "prize_money": int(money.replace(",", "")), "parser": RANKINGS_PARSER}
            for name, rank, money in RANKING_ROW.findall(current_table(rev["slots"]["main"]["*"]))]
