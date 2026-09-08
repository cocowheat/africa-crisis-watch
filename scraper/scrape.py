# -*- coding: utf-8 -*-
"""
Africa Crisis Watch - data collector
====================================
Pulls security incidents (terrorism, armed conflict, kidnapping/abduction)
from public RSS / Atom feeds covering Africa, then classifies, geo-tags,
scores and de-duplicates them into the JSON consumed by the front end.

Usage:
    python scrape.py            # fetch and write ../data/
    python scrape.py --dry-run  # print stats only, write nothing
"""

from __future__ import annotations

import concurrent.futures as futures
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "data"))

# Some publishers return 403 to a Chrome UA and only serve real XML to Safari.
UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
TIMEOUT = 15
MAX_ITEMS = 900
KEEP_DAYS = 90

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
# (source name, feed url, default country hint)
FEEDS = [
    # --- Pan-African / topical ---
    ("AllAfrica · Conflict", "https://allafrica.com/tools/headlines/rdf/conflict/headlines.rdf", ""),
    ("AllAfrica · Terrorism", "https://allafrica.com/tools/headlines/rdf/terrorism/headlines.rdf", ""),
    ("AllAfrica · Africa", "https://allafrica.com/tools/headlines/rdf/africa/headlines.rdf", ""),
    # --- Per country ---
    ("AllAfrica · Nigeria", "https://allafrica.com/tools/headlines/rdf/nigeria/headlines.rdf", "Nigeria"),
    ("AllAfrica · Mali", "https://allafrica.com/tools/headlines/rdf/mali/headlines.rdf", "Mali"),
    ("AllAfrica · Niger", "https://allafrica.com/tools/headlines/rdf/niger/headlines.rdf", "Niger"),
    ("AllAfrica · Chad", "https://allafrica.com/tools/headlines/rdf/chad/headlines.rdf", "Chad"),
    ("AllAfrica · Somalia", "https://allafrica.com/tools/headlines/rdf/somalia/headlines.rdf", "Somalia"),
    ("AllAfrica · Ethiopia", "https://allafrica.com/tools/headlines/rdf/ethiopia/headlines.rdf", "Ethiopia"),
    ("AllAfrica · Sudan", "https://allafrica.com/tools/headlines/rdf/sudan/headlines.rdf", "Sudan"),
    ("AllAfrica · Mozambique", "https://allafrica.com/tools/headlines/rdf/mozambique/headlines.rdf", "Mozambique"),
    ("AllAfrica · Cameroon", "https://allafrica.com/tools/headlines/rdf/cameroon/headlines.rdf", "Cameroon"),
    ("AllAfrica · Libya", "https://allafrica.com/tools/headlines/rdf/libya/headlines.rdf", "Libya"),
    ("AllAfrica · Kenya", "https://allafrica.com/tools/headlines/rdf/kenya/headlines.rdf", "Kenya"),
    ("AllAfrica · Uganda", "https://allafrica.com/tools/headlines/rdf/uganda/headlines.rdf", "Uganda"),
    # --- Think tanks / institutions ---
    ("International Crisis Group", "https://www.crisisgroup.org/rss.xml", ""),
    ("FDD Long War Journal", "https://www.longwarjournal.org/feed", ""),
    ("North Africa Post", "https://northafricapost.com/feed/", ""),
    ("Libya Herald", "https://www.libyaherald.com/feed/", "Libya"),
    ("Burkina 24", "https://burkina24.com/feed/", "Burkina Faso"),
    ("Sahel Intel", "https://sahelintel.com/feed/", ""),
    ("Horn Diplomat", "https://horndiplomat.com/feed/", ""),
    # --- Country / conflict-belt specialists ---
    ("HumAngle", "https://humanglemedia.com/feed/", ""),
    ("Somali Current", "https://somalicurrent.com/feed/", "Somalia"),
    ("Radio Dalsan", "https://www.radiodalsan.com/feed/", "Somalia"),
    ("Ethiopia Observer", "https://www.ethiopiaobserver.com/feed/", "Ethiopia"),
    ("IOL News", "https://www.iol.co.za/rss", "South Africa"),
    ("Radio Tamazuj", "https://www.radiotamazuj.org/feed/", "South Sudan"),
    ("Sudans Post", "https://www.sudanspost.com/feed/", "Sudan"),
    ("Ethiopian Monitor", "https://www.ethiopianmonitor.com/feed/", "Ethiopia"),
    ("TchadInfos", "https://www.tchadinfos.com/feed/", "Chad"),
    ("Journal du Cameroun", "https://www.journalducameroun.com/feed/", "Cameroon"),
    # --- Regional media ---
    ("Premium Times", "https://www.premiumtimesng.com/feed", "Nigeria"),
    ("Daily Post", "https://dailypost.ng/feed/", "Nigeria"),
    ("ThisDay Live", "https://www.thisdaylive.com/feed/", "Nigeria"),
    ("BusinessDay", "https://businessday.ng/feed/", "Nigeria"),
    ("Sun News Online", "https://www.sunnewsonline.com/feed/", "Nigeria"),
    ("Punch Nigeria", "https://punchng.com/feed/", "Nigeria"),
    ("Vanguard Nigeria", "https://www.vanguardngr.com/feed/", "Nigeria"),
    ("Channels TV", "https://www.channelstv.com/feed/", "Nigeria"),
    ("Blueprint Nigeria", "https://blueprint.ng/feed/", "Nigeria"),
    ("Daily Trust", "https://dailytrust.com/feed/", "Nigeria"),
    ("Sahara Reporters", "https://saharareporters.com/rss.xml", "Nigeria"),
    ("ICIR Nigeria", "https://www.icirnigeria.org/feed/", "Nigeria"),
    ("Somalia Guardian", "https://www.somaliguardian.com/feed/", "Somalia"),
    ("Dabanga Sudan", "https://www.dabangasudan.org/en/feed/", "Sudan"),
    ("Anadolu · Africa", "https://www.aa.com.tr/en/rss/default?cat=africa", ""),
    ("Africanews", "https://www.africanews.com/feed", ""),
]

# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------
COUNTRY_MAP = {
    "nigeria": ("Nigeria", "West Africa"),
    "nigéria": ("Nigeria", "West Africa"),
    "ghana": ("Ghana", "West Africa"),
    "benin": ("Benin", "West Africa"),
    "togo": ("Togo", "West Africa"),
    "cote d'ivoire": ("Côte d'Ivoire", "West Africa"),
    "ivory coast": ("Côte d'Ivoire", "West Africa"),
    "senegal": ("Senegal", "West Africa"),
    "sénégal": ("Senegal", "West Africa"),
    "guinea-bissau": ("Guinea-Bissau", "West Africa"),
    "sierra leone": ("Sierra Leone", "West Africa"),
    "liberia": ("Liberia", "West Africa"),
    "gambia": ("Gambia", "West Africa"),
    "guinea": ("Guinea", "West Africa"),
    "mali": ("Mali", "Sahel"),
    "malí": ("Mali", "Sahel"),
    "burkina faso": ("Burkina Faso", "Sahel"),
    "burkina": ("Burkina Faso", "Sahel"),
    "niger": ("Niger", "Sahel"),
    "chad": ("Chad", "Sahel"),
    "tchad": ("Chad", "Sahel"),
    "mauritania": ("Mauritania", "Sahel"),
    "mauritanie": ("Mauritania", "Sahel"),
    "sudan": ("Sudan", "Horn of Africa"),
    "south sudan": ("South Sudan", "Horn of Africa"),
    "somalia": ("Somalia", "Horn of Africa"),
    "somaliland": ("Somaliland", "Horn of Africa"),
    "ethiopia": ("Ethiopia", "Horn of Africa"),
    "eritrea": ("Eritrea", "Horn of Africa"),
    "djibouti": ("Djibouti", "Horn of Africa"),
    "kenya": ("Kenya", "Horn of Africa"),
    "uganda": ("Uganda", "Horn of Africa"),
    "libya": ("Libya", "North Africa"),
    "libye": ("Libya", "North Africa"),
    "egypt": ("Egypt", "North Africa"),
    "tunisia": ("Tunisia", "North Africa"),
    "algeria": ("Algeria", "North Africa"),
    "algérie": ("Algeria", "North Africa"),
    "morocco": ("Morocco", "North Africa"),
    "maroc": ("Morocco", "North Africa"),
    "western sahara": ("Western Sahara", "North Africa"),
    "dr congo": ("DR Congo", "Central Africa"),
    "democratic republic of the congo": ("DR Congo", "Central Africa"),
    "congo-kinshasa": ("DR Congo", "Central Africa"),
    "democratic republic of congo": ("DR Congo", "Central Africa"),
    "rdc": ("DR Congo", "Central Africa"),
    "central african republic": ("Central African Republic", "Central Africa"),
    "centrafrique": ("Central African Republic", "Central Africa"),
    "cameroon": ("Cameroon", "Central Africa"),
    "cameroun": ("Cameroon", "Central Africa"),
    "congo-brazzaville": ("Congo-Brazzaville", "Central Africa"),
    "gabon": ("Gabon", "Central Africa"),
    "equatorial guinea": ("Equatorial Guinea", "Central Africa"),
    "rwanda": ("Rwanda", "Central Africa"),
    "burundi": ("Burundi", "Central Africa"),
    "mozambique": ("Mozambique", "Southern Africa"),
    "zimbabwe": ("Zimbabwe", "Southern Africa"),
    "zambia": ("Zambia", "Southern Africa"),
    "malawi": ("Malawi", "Southern Africa"),
    "tanzania": ("Tanzania", "Southern Africa"),
    "angola": ("Angola", "Southern Africa"),
    "south africa": ("South Africa", "Southern Africa"),
    "namibia": ("Namibia", "Southern Africa"),
    "botswana": ("Botswana", "Southern Africa"),
    "madagascar": ("Madagascar", "Southern Africa"),
    "eswatini": ("Eswatini", "Southern Africa"),
    "lesotho": ("Lesotho", "Southern Africa"),
}
# Longest key first so "Niger" never wins over "Nigeria".
COUNTRY_KEYS = sorted(COUNTRY_MAP.keys(), key=len, reverse=True)

REGION_TERMS = {
    "sahel": "Sahel",
    "west africa": "West Africa",
    "horn of africa": "Horn of Africa",
    "central africa": "Central Africa",
    "north africa": "North Africa",
    "southern africa": "Southern Africa",
    "east africa": "Horn of Africa",
    "lake chad": "Central Africa",
    "great lakes": "Central Africa",
    "maghreb": "North Africa",
    "africa": "",
}

# ---------------------------------------------------------------------------
# Classification lexicons (English / French / Spanish)
# ---------------------------------------------------------------------------
CATEGORY_RULES = [
    ("terrorism", "Terrorism", [
        "terror", "terrorist", "jihadist", "jihadi", "jihad", "boko haram", "iswap",
        "al-shabaab", "al shabaab", "shabaab", "al-qaeda", "al qaeda", "jnim", "isgs",
        "isis", "isil", "islamic state", "daesh", "suicide bomber", "suicide bombing",
        "ied", "improvised explosive", "extremist", "insurgent", "insurgency",
        "militant group", "jama'at nusrat", "ansarul", "moorish",
        "attentat", "djihadiste", "djihad", "terroriste", "islamiste",
        "kamikaze", "engin explosif", "extrémiste",
        "atentado", "yihadista", "yihad", "terrorista", "terrorismo",
        "Estado Islámico", "Al Qaeda", "insurgencia", "suicida",
    ]),
    ("kidnapping", "Kidnapping & Abduction", [
        "kidnap", "kidnappers", "kidnapping", "abduct", "abduction", "abductors",
        "abducted", "abducting", "abducts", "hostage", "ransom", "captive",
        "captivity", "captives", "snatched", "in captivity", "chibok", "dapchi",
        "schoolchildren", "school girls", "schoolgirls", "bandits", "banditry",
        "cattle rustl", "held hostage", "rescued from", "freed after",
        "human trafficking", "trafficked", "kidnappings",
        "enlèvement", "enlevé", "otages", "rançon", "captifs", "ravisseurs",
        "secuestro", "secuestrados", "secuestradas", "rehenes", "rescate",
        "secuestradores", "privados de libertad", "raptados",
    ]),
    ("conflict", "Armed Conflict", [
        "war", "conflict", "clash", "clashes", "fighting", "battle", "gunfight",
        "attack", "attacked", "offensive", "airstrike", "air strike", "shelling",
        "artillery", "militia", "rebel", "rebels", "armed group", "armed men",
        "gunmen", "ambush", "raid", "massacre", "coup", "mutiny", "peacekeeping",
        "peacekeeper", "minusca", "unmiss", "rsf", "rapid support forces",
        "wagner", "mercenar", "drone strike", "mass killing", "displaced",
        "refugee", "casualt", "killed", "wounded", "slaughter",
        "affrontements", "combats", "attaque", "frappe", "milice", "rebelles",
        "groupe armé", "hommes armés", "embuscade", "massacre", "putsch",
        "déplacés", "réfugiés", "tués", "blessés", "conflit", "guerre",
        "ataque", "combates", "enfrentamientos", "milicias", "rebeldes",
        "grupo armado", "hombres armados", "emboscada", "masacre", "golpe",
        "desplazados", "refugiados", "asesinados", "muertos", "conflicto",
        "guerra",
    ]),
]
CATEGORY_META = {
    "terrorism": {"label": "Terrorism", "color": "#B91C1C"},
    "conflict": {"label": "Armed Conflict", "color": "#C2410C"},
    "kidnapping": {"label": "Kidnapping & Abduction", "color": "#7C3AED"},
    "other": {"label": "Other Security News", "color": "#475569"},
}

# When a headline carries no African place name at all, one of these must appear.
AFRICA_ANCHORS = [
    "africa", "african", "sahel", "boko haram", "iswap", "al-shabaab", "al-shabab",
    "jnim", "isgs", "iscap", "al qaeda", "islamic state", "isis", "adf", "m23",
    "rsf", "janjaweed", "wagner", "africom", "ecowas", "au summit", "african union",
    "bandits", "banditry", "kidnappers", "kidnapping", "herders", "fulani", "tuareg",
    "azawad", "jihadist", "jihadists", "insurgency", "insurgents", "militants",
    "coup", "junta", "peacekeeping", "humanitarian", "idps", "displaced",
    "lagos", "abuja", "borno", "kano", "sokoto", "zamfara", "kaduna", "nairobi",
    "mogadishu", "khartoum", "juba", "addis ababa", "kinshasa", "bamako",
    "ouagadougou", "niamey", "ndjamena", "tripoli", "tunis", "algiers", "accra",
    "dakar", "abidjan", "kampala", "goma", "bukavu", "cabo delgado", "maputo",
    "harare", "lusaka", "dodoma", "luanda", "windhoek", "gaborone", "antananarivo",
]

# Obvious non-African toponyms: kills syndicated world news in local papers.
NON_AFRICA_PLACES = [
    "london", "britain", "british", "portsmouth", "manchester", "washington",
    "new york", "miami", "texas", "california", "canada", "mexico", "brazil",
    "paris", "brussels", "geneva", "berlin", "madrid", "rome", "warsaw", "kyiv",
    "moscow", "russia", "beijing", "china", "delhi", "india", "pakistan",
    "islamabad", "kabul", "tehran", "iran", "baghdad", "damascus", "beirut",
    "tel aviv", "israel", "gaza", "riyadh", "doha", "dubai", "tokyo", "seoul",
    "canberra", "sydney", "australia", "jakarta", "manila", "bangkok", "hanoi",
]

FATALITY_PATTERNS = [
    r"(?:at least|more than|about|some|over|nearly|around)\s+(\d{1,4})\s+(?:people\s+)?(?:were\s+)?(?:killed|dead|slain|shot dead)",
    r"(\d{1,4})\s+(?:people\s+)?(?:were\s+)?(?:killed|dead|slain|murdered|shot dead|massacred)",
    r"(?:kills?|killed|slays?|slain|massacres?)\s+(?:at least\s+|some\s+|about\s+|over\s+)?(\d{1,4})",
    r"death\s+toll[^0-9]{0,30}(\d{1,4})",
    r"(\d{1,4})\s+(?:bodies|corpses|victims)",
    r"(\d{1,4})\s+dead",
    r"(?:au moins|plus de|environ)\s+(\d{1,4})\s+(?:personnes\s+)?(?:tuées|morts|tués)",
    r"(\d{1,4})\s+(?:personnes\s+)?(?:tuées|morts|tués)",
    r"(\d{1,4})\s+décès",
    r"(\d{1,4})\s+(?:muertos|asesinados|fallecidos|víctimas)",
    r"(?:al menos|más de)\s+(\d{1,4})\s+(?:muertos|asesinados)",
]
SEVERE_WORDS = [
    "massacre", "slaughter", "dozens", "scores", "mass killing", "carnage",
    "bloodbath", "tuerie", "carnage", "massacre", "dizaines",
]
SEVERITY_LABELS = ("Moderate", "High", "Severe")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def strip_tags(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fn in (
        lambda: parsedate_to_datetime(raw),
        lambda: datetime.fromisoformat(raw.replace("Z", "+00:00")),
    ):
        try:
            dt = fn()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", "ignore")).hexdigest()[:12]


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def looks_like_feed(payload: bytes) -> bool:
    """Some CMSs prepend a UTF-8 BOM / whitespace to the XML, so strip first."""
    head = payload[:1500].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return (
        head.startswith(b"<?xml")
        or head.startswith(b"<rss")
        or head.startswith(b"<feed")
        or b"<rdf:rdf" in head
    )


# Trip the breaker after repeated failures so timeouts cannot stall the run.
_host_fail: dict[str, int] = {}
_article_fail: dict[str, int] = {}


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url


def fetch(url: str, retries: int = 1) -> bytes | None:
    """Try each UA until the response actually looks like RSS/Atom; then retry."""
    host = host_of(url)
    if _host_fail.get(host, 0) >= 3:
        print(f"    ! skipped (host breaker open) {url[:70]}")
        return None
    last = "response was not a feed"
    for attempt in range(retries + 1):
        for ua in UA_POOL:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": ua,
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    payload = resp.read()
                if looks_like_feed(payload):
                    _host_fail[host] = 0
                    return payload
                last = "response was not a feed"
            except Exception as exc:
                last = f"{type(exc).__name__}: {str(exc)[:40]}"
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    _host_fail[host] = _host_fail.get(host, 0) + 1
    print(f"    ! fetch failed {url[:70]} -> {last}")
    return None


NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
    "atom": "http://www.w3.org/2005/Atom",
}


def first(node: ET.Element, *paths: str) -> str:
    for path in paths:
        found = node.find(path, NS)
        if found is not None:
            if found.text and found.text.strip():
                return found.text.strip()
            href = found.get("href")
            if href:
                return href.strip()
    return ""


def parse_feed(payload: bytes, source: str, hint_country: str) -> list[dict]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        text = payload.decode("utf-8", "ignore")
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text).strip()
        # Drop control characters that XML 1.0 forbids (some CMSs emit them).
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            print(f"    ! parse failed {source}: {exc}")
            return []

    nodes = root.findall(".//item")
    if not nodes:
        nodes = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    if not nodes:
        nodes = root.findall(".//{http://purl.org/rss/1.0/}item")

    out = []
    for node in nodes:
        title = strip_tags(first(node, "title", "{http://www.w3.org/2005/Atom}title"))
        if not title:
            continue
        link = first(node, "link", "{http://www.w3.org/2005/Atom}link", "guid")
        excerpt = strip_tags(first(node, "description", "{http://www.w3.org/2005/Atom}summary"))
        # WordPress-style feeds carry the whole article in content:encoded.
        # Prefer it, or we only ever see the 200-character editorial teaser.
        full = strip_tags(first(node, "content:encoded", "{http://www.w3.org/2005/Atom}content"))
        published = first(
            node,
            "pubDate",
            "{http://www.w3.org/2005/Atom}updated",
            "{http://www.w3.org/2005/Atom}published",
            "dc:date",
            "{http://purl.org/dc/elements/1.1/}date",
        )
        image = ""
        for path in ("media:thumbnail", "media:content", "enclosure"):
            found = node.find(path, NS)
            if found is not None:
                image = found.get("url") or found.get(
                    "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"
                ) or ""
                if image:
                    break
        out.append(
            {
                "title": title,
                "url": link,
                "summary": excerpt,
                "body": full,
                "published": parse_date(published),
                "source": source,
                "hint_country": hint_country,
                "image": image,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Full-text backfill
# ---------------------------------------------------------------------------
# Feeds without content:encoded (Punch, AllAfrica, Crisis Group...) only give a
# teaser, so visit the article page and pull the paragraphs out.
MAX_BODY = 9000
SUMMARY_CHARS = 400
BODY_MIN = 700

_JUNK = (
    "share this", "read more", "subscribe", "advertisement", "related stor",
    "follow us", "copyright", "all rights reserved", "click here", "sign up",
    "photo:", "credit:", "sponsored", "join our", "newsletter", "cookie",
)
# Leftover template / script fragments that leak into <p> on some CMSs.
_CODE_MARKERS = ("utm_", "<?", "?>", '">', "function(", "=>", "var ", "download our",
                 "download the app", "lite app", ".style", "getelementbyid")


def extract_article(html_src: str) -> str:
    src = re.sub(
        r"<(script|style|noscript|nav|header|footer|aside|form|svg)[^>]*>.*?</\1>",
        " ",
        html_src,
        flags=re.S | re.I,
    )
    parts = []
    for para in re.findall(r"<p[^>]*>(.*?)</p>", src, flags=re.S | re.I):
        text = strip_tags(para)
        if len(text) < 60:
            continue
        low = text.lower()[:90]
        if any(j in low for j in _JUNK):
            continue
        if any(m in text.lower() for m in _CODE_MARKERS):
            continue
        # Real prose: mostly letters, spaces and normal punctuation.
        letters = sum(1 for ch in text if ch.isalpha() or ch.isspace())
        if letters / max(len(text), 1) < 0.75:
            continue
        parts.append(text)
        if sum(len(p) for p in parts) > MAX_BODY:
            break
    return "\n\n".join(parts)[:MAX_BODY]


def fetch_article(url: str) -> str:
    # Article pages fail individually far more often than feeds, so give each
    # host a higher tolerance before opening the breaker.
    host = host_of(url)
    if _article_fail.get(host, 0) >= 6 or not url.startswith("http"):
        return ""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA_POOL[1],
                "Accept": "text/html,application/xhtml+xml,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if ctype and "html" not in ctype.lower():
                return ""
            raw = resp.read(3_000_000)
    except Exception:
        _article_fail[host] = _article_fail.get(host, 0) + 1
        return ""
    _article_fail[host] = 0
    try:
        return extract_article(raw.decode("utf-8", "ignore"))
    except Exception:
        return ""


def load_body_cache() -> dict:
    path = os.path.join(DATA_DIR, "bodies.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


def enrich_bodies(items: list[dict]) -> None:
    """Fill in missing article text, reusing the cache so we never refetch."""
    cache = load_body_cache()
    targets = []
    for it in items:
        cached = cache.get(it["id"], "")
        if len(cached) >= BODY_MIN:
            it["body"] = cached
        elif len(it.get("body", "")) < BODY_MIN:
            targets.append(it)
    if not targets:
        return
    print(f"    backfilling full text for {len(targets)} records ...")
    with futures.ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch_article, it["url"]): it for it in targets}
        for job in futures.as_completed(jobs):
            it = jobs[job]
            text = job.result()
            if len(text) >= BODY_MIN:
                it["body"] = text
                cache[it["id"]] = text
    # Keep the cache from growing forever.
    if len(cache) > 4000:
        keep = {i["id"] for i in items}
        cache = {k: v for k, v in cache.items() if k in keep}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "bodies.json"), "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Semantic analysis
# ---------------------------------------------------------------------------
def detect_country(text: str, hint: str = "") -> tuple[str, str]:
    if hint and hint.lower() in COUNTRY_MAP:
        return COUNTRY_MAP[hint.lower()]
    low = text.lower()
    for key in COUNTRY_KEYS:
        if re.search(r"\b" + re.escape(key) + r"\b", low):
            return COUNTRY_MAP[key]
    return "", ""


def detect_region(text: str) -> str:
    low = text.lower()
    for term, region in REGION_TERMS.items():
        if term in low and region:
            return region
    return ""


def _kw_pattern(word: str) -> str:
    """
    Short tokens (war / coup / ied / rsf) need a whole-word match or they hit
    warm, coupon and friends. Stems of 5+ letters may take 0-3 inflection
    chars, so kidnap matches kidnapped and abduct matches abduction -- while
    plain substring matching stays off the table.
    """
    w = re.escape(word.lower())
    if len(word) >= 5:
        return r"(?<![a-z])" + w + r"[a-z]{0,3}(?![a-z])"
    return r"(?<![a-z])" + w + r"(?![a-z])"


def _kw_hits(text: str, words: list[str]) -> int:
    return sum(1 for word in words if re.search(_kw_pattern(word), text))


def detect_category(text: str) -> str:
    low = text.lower()
    scores = {key: _kw_hits(low, words) for key, _label, words in CATEGORY_RULES}
    top = max(scores, key=lambda k: scores[k])
    if scores[top] == 0:
        return "other"
    # Priority: kidnapping > terrorism > conflict. When a jihadist group
    # abducts villagers, "abducted" is the attribute researchers search on.
    if scores["kidnapping"] > 0:
        return "kidnapping"
    if scores["terrorism"] > 0:
        return "terrorism"
    return "conflict"


def detect_fatalities(text: str) -> int:
    low = text.lower()
    best = 0
    for pattern in FATALITY_PATTERNS:
        for match in re.finditer(pattern, low):
            try:
                value = int(match.group(1))
            except (IndexError, ValueError):
                continue
            if 0 < value <= 5000 and value > best:
                best = value
    return best


def severity_of(text: str, fatalities: int) -> tuple[str, int]:
    low = text.lower()
    if fatalities >= 50:
        score = 3
    elif fatalities >= 15:
        score = 2
    elif fatalities >= 1:
        score = 1
    else:
        score = 0
    if any(word in low for word in SEVERE_WORDS):
        score = max(score, 2)
    score = min(score, 2)
    return SEVERITY_LABELS[score], score


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def collect() -> list[dict]:
    raw_items: list[dict] = []
    slow: list[tuple] = []
    rest: list[tuple] = []
    for entry in FEEDS:
        (slow if "allafrica.com" in entry[1] else rest).append(entry)

    # AllAfrica throttles concurrent connections hard, so walk it one at a time
    # instead of burning the host breaker with a parallel burst.
    for name, url, hint in slow:
        payload = fetch(url)
        if payload:
            got = parse_feed(payload, name, hint)
            print(f"    - {name}: {len(got)} items")
            raw_items.extend(got)
        time.sleep(0.3)

    with futures.ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(fetch, url): (name, hint) for name, url, hint in rest}
        for job in futures.as_completed(jobs):
            name, hint = jobs[job]
            payload = job.result()
            if not payload:
                continue
            got = parse_feed(payload, name, hint)
            print(f"    - {name}: {len(got)} items")
            raw_items.extend(got)
    return raw_items


def build(raw_items: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=KEEP_DAYS)
    seen: dict[str, dict] = {}
    stats = {"total_raw": len(raw_items), "dropped_old": 0, "dropped_offtopic": 0, "dup": 0}

    for item in raw_items:
        published = item["published"]
        if published and published < cutoff:
            stats["dropped_old"] += 1
            continue
        blob = f"{item['title']} {item['summary']} {item['body'][:1200]}"
        low = blob.lower()

        # Look for explicit African geography first, then fall back to the
        # source's default country.
        country, region = detect_country(blob, "")
        explicit_country = bool(country)
        if not region:
            region = detect_region(blob)
        if not explicit_country and not region:
            # Local papers syndicate world news: require an African anchor and
            # reject headlines that only mention foreign places.
            if not _kw_hits(low, AFRICA_ANCHORS) or _kw_hits(low, NON_AFRICA_PLACES):
                stats["dropped_offtopic"] += 1
                continue
        if not country and item["hint_country"]:
            country, region = detect_country(blob, item["hint_country"])
        if not region:
            stats["dropped_offtopic"] += 1
            continue

        category = detect_category(blob)
        if category == "other" and not _kw_hits(
            low,
            [
                "attack", "kill", "killed", "gun", "gunmen", "militia", "armed",
                "security", "violence", "violent", "protest", "unrest", "riot",
                "troops", "soldiers", "curfew",
                "attaque", "tué", "armé", "violence", "sécurité", "milice", "conflit",
                "ataque", "asesinados", "ejército", "militares",
            ],
        ):
            stats["dropped_offtopic"] += 1
            continue

        key = normalize_title(item["title"])[:110]
        if key in seen:
            stats["dup"] += 1
            continue

        fatalities = detect_fatalities(blob)
        sev_label, sev_score = severity_of(blob, fatalities)
        body = item["body"] or ""
        excerpt = item["summary"] or ""
        if not excerpt:
            excerpt = body[:SUMMARY_CHARS]
        seen[key] = {
            "id": md5(key),
            "title": item["title"],
            "summary": excerpt[:SUMMARY_CHARS] or
                       "No summary supplied by the source - open the original to read more.",
            "body": body[:MAX_BODY],
            "url": item["url"],
            "source": item["source"],
            "image": item["image"],
            "published": (published or now).isoformat(),
            "category": category,
            "category_label": CATEGORY_META[category]["label"],
            "region": region,
            "country": country,
            "fatalities": fatalities,
            "severity": sev_label,
            "severity_score": sev_score,
        }

    items = sorted(seen.values(), key=lambda x: x["published"], reverse=True)[:MAX_ITEMS]
    print(
        f"    raw {stats['total_raw']} -> kept {len(items)} "
        f"(stale {stats['dropped_old']} / off-topic {stats['dropped_offtopic']} / dupes {stats['dup']})"
    )
    return items


def compute_stats(items: list[dict]) -> dict:
    by_category: dict[str, int] = {}
    by_region: dict[str, int] = {}
    by_country: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_day: dict[str, int] = {}
    fatalities = 0
    fulltext = 0
    chars = 0
    for it in items:
        by_category[it["category"]] = by_category.get(it["category"], 0) + 1
        by_region[it["region"]] = by_region.get(it["region"], 0) + 1
        by_country[it["country"] or "Unspecified"] = by_country.get(it["country"] or "Unspecified", 0) + 1
        by_source[it["source"]] = by_source.get(it["source"], 0) + 1
        by_day[it["published"][:10]] = by_day.get(it["published"][:10], 0) + 1
        fatalities += it["fatalities"]
        chars += len(it.get("body", ""))
        if len(it.get("body", "")) >= BODY_MIN:
            fulltext += 1
    return {
        "total": len(items),
        "fatalities": fatalities,
        "fulltext": fulltext,
        "avg_body": int(chars / len(items)) if items else 0,
        "countries": len([k for k in by_country if k != "Unspecified"]),
        "sources": len(by_source),
        "by_category": by_category,
        "by_region": by_region,
        "by_country": dict(sorted(by_country.items(), key=lambda kv: -kv[1])[:25]),
        "by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
        "by_day": dict(sorted(by_day.items())),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def merge_history(items: list[dict]) -> list[dict]:
    path = os.path.join(DATA_DIR, "history.json")
    history = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                history = json.load(fh)
        except Exception:
            history = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = {
        "date": today,
        "total": len(items),
        "terrorism": sum(1 for i in items if i["category"] == "terrorism"),
        "conflict": sum(1 for i in items if i["category"] == "conflict"),
        "kidnapping": sum(1 for i in items if i["category"] == "kidnapping"),
        "fatalities": sum(i["fatalities"] for i in items),
    }
    history = [h for h in history if h.get("date") != today]
    history.append(entry)
    return sorted(history, key=lambda h: h["date"])[-60:]


def main() -> int:
    dry = "--dry-run" in sys.argv
    print("[1/3] fetching feeds ...")
    raw = collect()
    print("[2/3] cleaning / classifying / geo-tagging ...")
    items = build(raw)
    if not items:
        print("! no items collected - keeping the previous dataset.")
        return 1
    if "--no-bodies" not in sys.argv:
        enrich_bodies(items)
    stats = compute_stats(items)
    history = merge_history(items)

    print(
        f"[3/3] {stats['total']} items | {len(stats['by_region'])} regions | "
        f"{stats['countries']} countries | {stats['fatalities']} reported fatalities"
    )
    print(
        f"      full text: {stats['fulltext']}/{stats['total']} records, "
        f"average {stats['avg_body']} characters"
    )
    for region, count in sorted(stats["by_region"].items(), key=lambda kv: -kv[1]):
        print(f"      {region:<18} {count}")
    for cat, count in sorted(stats["by_category"].items(), key=lambda kv: -kv[1]):
        print(f"      {CATEGORY_META[cat]['label']:<24} {count}")

    if dry:
        return 0

    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {"stats": stats, "items": items, "history": history}
    with open(os.path.join(DATA_DIR, "news.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "news.js"), "w", encoding="utf-8") as fh:
        fh.write("window.CRISIS_DATA = ")
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")
    print(f"      wrote {os.path.join(DATA_DIR, 'news.json')} / news.js")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
