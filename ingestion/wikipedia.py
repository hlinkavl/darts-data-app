"""Wikipedia / Wikidata: tournament pages (draws, results) and player background. Content is CC BY-SA."""

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


def _search_player(client: PoliteClient, name: str) -> str | None:
    """Wikidata entity ID of a darts player, or None when no confident match exists."""
    hits = client.get_json(
        WIKIDATA_API,
        {"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 5, "format": "json"},
    ).get("search", [])
    for hit in hits:
        if "dart" in hit.get("description", "").lower():
            return hit["id"]
    return None


def fetch_player_background(client: PoliteClient, name: str) -> dict:
    """Date of birth, citizenship, nickname, image and English Wikipedia intro for one player."""
    qid = _search_player(client, name)
    if qid is None:
        return {"name": name, "wikidata_id": None}

    entity = client.get_json(
        WIKIDATA_API,
        {"action": "wbgetentities", "ids": qid, "props": "claims|sitelinks|descriptions", "languages": "en", "format": "json"},
    )["entities"][qid]

    record = {"name": name, "wikidata_id": qid, "description": entity.get("descriptions", {}).get("en", {}).get("value")}
    for pid, field in PROPS.items():
        values = []
        for claim in entity.get("claims", {}).get(pid, []):
            value = claim["mainsnak"].get("datavalue", {}).get("value")
            if isinstance(value, dict):
                value = value.get("time") or value.get("id") or value.get("text")
            if value:
                values.append(value)
        record[field] = values

    wiki_title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
    record["enwiki_title"] = wiki_title
    if wiki_title:
        extract = client.get_json(
            WIKI_API,
            {"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "titles": wiki_title,
             "format": "json", "redirects": 1},
        )
        pages = extract.get("query", {}).get("pages", {})
        record["intro"] = next(iter(pages.values()), {}).get("extract")
    return record
