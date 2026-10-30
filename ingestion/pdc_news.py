"""Official PDC news (pdc.tv RSS): the 20 latest articles with full text.

The feed covers only about 4-7 days, so every refresh stores what it sees and bronze keeps every article ever
fetched (deduplicated by link). Article text is used only as input for AI summaries; the app shows the
summaries with a link to the original, never the full text.
"""

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from .http import PoliteClient

FEED = "https://www.pdc.tv/rss.xml"


def _text(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment or "", flags=re.S)
    fragment = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", fragment)
    return re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def fetch(client: PoliteClient) -> list[dict]:
    root = ET.fromstring(client.get_text(FEED, use_cache=False))
    items = []
    for it in root.iter("item"):
        get = lambda tag: (it.findtext(tag) or "").strip()
        published = parsedate_to_datetime(get("pubDate")).isoformat() if get("pubDate") else None
        items.append({"link": get("link"), "title": html.unescape(get("title")), "published": published,
                      "author": get("author"), "categories": [c.text for c in it.findall("category") if c.text],
                      "text": _text(get("description"))})
    return items
