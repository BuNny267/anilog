"""AniList GraphQL client with rate limiting and retries."""
import time, threading, requests
import config

ANILIST_URL = config.ANILIST_URL
TIMEOUT = config.REQUEST_TIMEOUT

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": f"AniLog/{config.APP_VERSION}",
    "Accept": "application/json",
    "Content-Type": "application/json",
})


class ApiError(Exception):
    pass


class RateLimitError(ApiError):
    pass


class NotFoundError(ApiError):
    pass


_lock = threading.Lock()
_last = 0.0


def _throttle():
    global _last
    with _lock:
        now = time.time()
        gap = now - _last
        if gap < config.ANILIST_MIN_INTERVAL:
            time.sleep(config.ANILIST_MIN_INTERVAL - gap)
        _last = time.time()


def _query(q, variables=None, retries=3):
    variables = variables or {}
    for attempt in range(retries):
        _throttle()
        try:
            resp = SESSION.post(ANILIST_URL, json={"query": q, "variables": variables},
                                timeout=TIMEOUT)
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise ApiError(f"Network error: {e}")
        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", 5))
            if attempt < retries - 1:
                time.sleep(wait)
                continue
            raise RateLimitError(f"Rate limited, wait {wait}s")
        if resp.status_code >= 500:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise ApiError(f"Server error {resp.status_code}")
        if resp.status_code == 404:
            raise NotFoundError("Not found")
        if resp.status_code != 200:
            try:
                err_data = resp.json()
                print(f"[AniList HTTP {resp.status_code}] {err_data}")
            except Exception:
                print(f"[AniList HTTP {resp.status_code}] {resp.text[:200]}")
            raise ApiError(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise ApiError(f"Invalid JSON: {e}")
        if data.get("errors"):
            msg = data["errors"][0].get("message", "Unknown error")
            print(f"[AniList Error] {msg}")
            if "not found" in msg.lower():
                raise NotFoundError(msg)
            raise ApiError(msg)
        return data.get("data", {})
    raise ApiError("Max retries exceeded")


LIST_FIELDS = """
  idMal
  title { userPreferred romaji english native }
  type format episodes seasonYear averageScore popularity
  coverImage { medium large extraLarge }
"""

FULL_FIELDS = LIST_FIELDS + """
  synonyms status season duration source
  startDate { year month day } endDate { year month day }
  studios(isMain: true) { nodes { name } }
  favourites genres tags { name }
  description(asHtml: false)
  trailer { id site }
  bannerImage
  nextAiringEpisode { episode airingAt }
  externalLinks { site url type }
"""

FMT = {"TV": "TV", "TV_SHORT": "TV", "MOVIE": "Movie", "SPECIAL": "Special",
       "OVA": "OVA", "ONA": "ONA", "MUSIC": "Music"}

REL_MAP = {"ADAPTATION": "Adaptation", "PREQUEL": "Prequel", "SEQUEL": "Sequel",
           "PARENT": "Parent", "SIDE_STORY": "Side Story", "CHARACTER": "Character",
           "SUMMARY": "Summary", "ALTERNATIVE": "Alternative", "SPIN_OFF": "Spin Off",
           "OTHER": "Other", "SOURCE": "Source", "COMPILATION": "Compilation",
           "CONTAINS": "Contains"}


def _trailer_url(t):
    if not t or not t.get("site") or not t.get("id"):
        return None
    if t["site"] == "youtube":
        return f"https://www.youtube.com/watch?v={t['id']}"
    if t["site"] == "dailymotion":
        return f"https://www.dailymotion.com/video/{t['id']}"
    return None


def _parse_streaming(links):
    """Extract official streaming platforms from externalLinks."""
    out, seen = [], set()
    for l in links or []:
        site, url = l.get("site"), l.get("url")
        if not site or not url or l.get("type") not in (None, "STREAMING"):
            continue
        key = site.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": site, "url": url, "site": site})
    return out[:6]


def _date(d):
    if not d or not d.get("year"):
        return None
    return f"{d['year']:04d}-{(d.get('month') or 1):02d}-{(d.get('day') or 1):02d}"


def _parse(node, full=False):
    if not node or not node.get("idMal"):
        return None
    t = node.get("title") or {}
    cover = node.get("coverImage") or {}
    year = node.get("seasonYear") or (node.get("startDate") or {}).get("year")
    out = {
        "mal_id": node["idMal"],
        "title": t.get("userPreferred") or t.get("english") or t.get("romaji") or t.get("native") or "Unknown",
        "title_english": t.get("english"),
        "title_japanese": t.get("native"),
        "title_romaji": t.get("romaji"),
        "type": FMT.get(node.get("format"), node.get("format")),
        "episodes": node.get("episodes"),
        "year": year,
        "score": node.get("averageScore"),
        "popularity": node.get("popularity"),
        "airing": node.get("status") == "RELEASING",
        "image_url": cover.get("extraLarge") or cover.get("large") or cover.get("medium"),
        "genres": node.get("genres") or [],
    }
    if full:
        out.update({
            "synonyms": node.get("synonyms") or [],
            "status": node.get("status"),
            "season": node.get("season"),
            "duration": node.get("duration"),
            "source": node.get("source"),
            "favorites": node.get("favourites"),
            "studios": [s["name"] for s in (node.get("studios") or {}).get("nodes", []) if s.get("name")],
            "synopsis": node.get("description") or "",
            "trailer_url": _trailer_url(node.get("trailer")),
            "banner_url": node.get("bannerImage"),
            "tags": [x.get("name") for x in (node.get("tags") or []) if x.get("name")],
            "streaming": _parse_streaming(node.get("externalLinks")),
            "aired_from": _date(node.get("startDate")),
            "aired_to": _date(node.get("endDate")),
            "next_episode": ({"episode": node["nextAiringEpisode"].get("episode"),
                              "airing_at": node["nextAiringEpisode"].get("airingAt")}
                             if node.get("nextAiringEpisode") else None),
        })
    return out


SEARCH_Q = f"""
query ($search: String, $limit: Int) {{
  Page(page: 1, perPage: $limit) {{
    media(search: $search, type: ANIME, isAdult: false, sort: SEARCH_MATCH) {{
      {LIST_FIELDS}
    }}
  }}
}}
"""


def search(q, limit=30):
    q = (q or "").strip()
    if not q:
        return []
    data = _query(SEARCH_Q, {"search": q, "limit": min(limit, 50)})
    return [m for m in (_parse(i) for i in (data.get("Page") or {}).get("media") or []) if m]


META_Q = f"""
query ($idMal: Int) {{
  Media(idMal: $idMal, type: ANIME) {{ {FULL_FIELDS} }}
}}
"""


def fetch_metadata(mal_id):
    data = _query(META_Q, {"idMal": int(mal_id)})
    media = data.get("Media")
    if not media:
        raise NotFoundError(f"Anime {mal_id} not found")
    parsed = _parse(media, full=True)
    if not parsed:
        raise NotFoundError(f"Anime {mal_id} has no MAL mapping")
    return parsed


CHARS_Q = """
query ($idMal: Int) {
  Media(idMal: $idMal, type: ANIME) {
    characters(sort: [ROLE, FAVOURITES_DESC], perPage: 25) {
      edges {
        role
        voiceActors(language: JAPANESE) { name { userPreferred } image { medium } language }
        voiceActors(language: ENGLISH) { name { userPreferred } image { medium } language }
        node { name { userPreferred } image { medium } }
      }
    }
  }
}
"""


def fetch_characters(mal_id):
    """Fetch characters with voice actors."""
    query = """
    query ($idMal: Int) {
      Media(idMal: $idMal, type: ANIME) {
        characters(sort: [ROLE, FAVOURITES_DESC], perPage: 30) {
          edges {
            role
            voiceActors {
              name { userPreferred }
              image { medium }
              language
            }
            node {
              name { userPreferred }
              image { medium }
            }
          }
        }
      }
    }
    """
    
    data = _query(query, {"idMal": int(mal_id)})
    media = data.get("Media")
    if not media:
        print(f"[Cast] No media found for {mal_id}")
        return []
    
    edges = (media.get("characters") or {}).get("edges") or []
    if not edges:
        print(f"[Cast] No characters found for {mal_id}")
        return []
    
    print(f"[Cast] Found {len(edges)} characters for {mal_id}")
    out = []
    
    for e in edges:
        node = e.get("node") or {}
        char_name = (node.get("name") or {}).get("userPreferred")
        if not char_name:
            continue
            
        char = {
            "name": char_name,
            "image": (node.get("image") or {}).get("medium"),
            "role": (e.get("role") or "SUPPORTING").capitalize(),
            "voice_actors": [],
        }
        
        # Collect all voice actors, prefer JP then EN
        voice_actors = e.get("voiceActors") or []
        jp_va = None
        en_va = None
        
        for va in voice_actors:
            name = (va.get("name") or {}).get("userPreferred")
            lang = (va.get("language") or "").lower()
            if not name:
                continue
                
            va_data = {
                "name": name,
                "image": (va.get("image") or {}).get("medium"),
                "lang": lang,
            }
            
            if lang in ("japanese", "jp", "ja"):
                jp_va = {**va_data, "lang": "jp"}
            elif lang in ("english", "en"):
                en_va = {**va_data, "lang": "en"}
        
        # Add JP first, then EN if available
        if jp_va:
            char["voice_actors"].append(jp_va)
        if en_va:
            char["voice_actors"].append(en_va)
        
        out.append(char)
    
    return out[:25]  # Limit to 25 characters


REL_Q = """
query ($idMal: Int) {
  Media(idMal: $idMal, type: ANIME) {
    relations {
      edges {
        relationType
        node {
          idMal title { userPreferred } type format episodes seasonYear
          coverImage { medium large }
        }
      }
    }
  }
}
"""


def relations(mal_id):
    data = _query(REL_Q, {"idMal": int(mal_id)})
    media = data.get("Media")
    if not media:
        return []
    out = []
    for e in (media.get("relations") or {}).get("edges") or []:
        n = e.get("node") or {}
        if not n.get("idMal"):
            continue
        cover = n.get("coverImage") or {}
        out.append({
            "relation": REL_MAP.get(e.get("relationType"),
                                    (e.get("relationType") or "Other").replace("_", " ").title()),
            "mal_id": n["idMal"], "related_id": n["idMal"],
            "title": (n.get("title") or {}).get("userPreferred") or "Unknown",
            "type": FMT.get(n.get("format"), n.get("format")),
            "year": n.get("seasonYear"), "episodes": n.get("episodes"),
            "image_url": cover.get("large") or cover.get("medium"),
        })
    return out


SCHEDULE_Q = f"""
query ($page: Int, $perPage: Int, $from: Int, $to: Int) {{
  Page(page: $page, perPage: $perPage) {{
    airingSchedules(airingAt_greater: $from, airingAt_lesser: $to, sort: TIME) {{
      airingAt episode
      media {{
        idMal title {{ userPreferred }} format episodes averageScore
        coverImage {{ medium large }}
        nextAiringEpisode {{ airingAt episode }}
      }}
    }}
  }}
}}
"""


def fetch_schedule(days=7):
    now = int(time.time())
    data = _query(SCHEDULE_Q, {"page": 1, "perPage": 100,
                               "from": now, "to": now + days * 86400})
    out = []
    for item in (data.get("Page") or {}).get("airingSchedules") or []:
        m = item.get("media") or {}
        if not m.get("idMal"):
            continue
        cover = m.get("coverImage") or {}
        nxt = m.get("nextAiringEpisode") or {}
        out.append({
            "mal_id": m["idMal"],
            "title": (m.get("title") or {}).get("userPreferred") or "Unknown",
            "image_url": cover.get("large") or cover.get("medium"),
            "episode": item.get("episode"),
            "airing_at": item.get("airingAt", 0),
            "type": FMT.get(m.get("format"), m.get("format")),
            "score": m.get("averageScore"),
            "next_episode": nxt.get("episode"),
            "next_episode_at": nxt.get("airingAt"),
        })
    out.sort(key=lambda x: x["airing_at"])
    return out


def current_season():
    from datetime import datetime
    now = datetime.now()
    m = now.month
    season = ("WINTER" if m in (1, 2, 3) else "SPRING" if m in (4, 5, 6)
              else "SUMMER" if m in (7, 8, 9) else "FALL")
    return season, now.year


DISC_Q = f"""
query ($season: MediaSeason, $year: Int, $format: MediaFormat, $sort: [MediaSort], $perPage: Int) {{
  Page(page: 1, perPage: $perPage) {{
    media(type: ANIME, isAdult: false, season: $season, seasonYear: $year,
          format: $format, sort: $sort) {{ {LIST_FIELDS} }}
  }}
}}
"""


def _discover(vars_, limit=20):
    v = dict(vars_)
    v["perPage"] = limit
    data = _query(DISC_Q, v)
    return [m for m in (_parse(i) for i in (data.get("Page") or {}).get("media") or []) if m]


def trending(limit=20):
    return _discover({"sort": ["TRENDING_DESC"]}, limit)


def seasonal(limit=20):
    s, y = current_season()
    return _discover({"season": s, "year": y, "sort": ["POPULARITY_DESC"]}, limit)


def popular(limit=20):
    return _discover({"sort": ["POPULARITY_DESC"]}, limit)


def top_rated(limit=20):
    return _discover({"sort": ["SCORE_DESC"]}, limit)


def upcoming(limit=20):
    return _discover({"sort": ["START_DATE_DESC"], "format": "TV"}, limit)


def top_movies(limit=20):
    return _discover({"format": "MOVIE", "sort": ["SCORE_DESC"]}, limit)

STAFF_Q = """
query ($idMal: Int) {
  Media(idMal: $idMal, type: ANIME) {
    staff(sort: [ROLE, ID], perPage: 12) {
      edges {
        role
        node { name { userPreferred } image { medium } }
      }
    }
  }
}
"""


def fetch_staff(mal_id):
    data = _query(STAFF_Q, {"idMal": int(mal_id)})
    media = data.get("Media")
    if not media:
        return []
    out = []
    for e in (media.get("staff") or {}).get("edges") or []:
        node = e.get("node") or {}
        name = (node.get("name") or {}).get("userPreferred")
        if not name:
            continue
        out.append({
            "name": name,
            "image": (node.get("image") or {}).get("medium"),
            "role": (e.get("role") or "Staff").split(",")[0].strip(),
        })
    return out[:12]