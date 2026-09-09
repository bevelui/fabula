# -*- coding: utf-8 -*-
"""Channel analysis. Uses YouTube's public per-channel RSS feed (no API key, no
scraping of video pages) to read recent uploads, then derives a lightweight style
profile. If YOUTUBE_API_KEY is set, richer stats can be layered on later.
"""
import re, datetime, collections
import xml.etree.ElementTree as ET
import httpx

_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"
_MEDIA = "{http://search.yahoo.com/mrss/}"

# small multilingual stopword set for keyword extraction
_STOP = set("""the a an and or of to in on for with at by from as is are was were be
this that these those you your my our their his her it its we they i he she
el la los las un una unos unas de del y o en con por para que se su sus lo al
le les je tu il elle nous vous ils de la le et ou un une des du en pour avec
der die das und oder ein eine den dem des im mit von zu auf fur ist
de het een en van voor met is op te""".split())


def _client():
    return httpx.Client(timeout=15, follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0 (FabulaBot; channel analysis)"})


def resolve_channel_id(url, log=lambda m: None):
    """Return a UC... channel id from a channel URL (handle, /channel/, /c/, /user/)."""
    m = re.search(r"/channel/(UC[\w-]{20,})", url)
    if m:
        return m.group(1)
    # fetch the channel page and pull the canonical channel id
    if not re.match(r"^https?://", url):
        url = "https://www.youtube.com/" + url.lstrip("/")
    with _client() as c:
        html = c.get(url).text
    # externalId is the channel's OWN id; canonical link is next most reliable.
    # A bare "channelId" can belong to a featured/linked channel, so try it last.
    for pat in (r'"externalId":"(UC[\w-]{20,})"',
                r'<link[^>]+rel="canonical"[^>]+href="https://www\.youtube\.com/channel/(UC[\w-]{20,})"',
                r'"channelId":"(UC[\w-]{20,})"',
                r'/channel/(UC[\w-]{20,})'):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    raise ValueError("could not resolve channel id from that URL")


def fetch_recent(channel_id):
    """Recent uploads from the public RSS feed: (channel_title, [entries])."""
    feed = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    with _client() as c:
        r = c.get(feed)
        r.raise_for_status()
        xml = r.text
    root = ET.fromstring(xml)
    title = (root.findtext(_ATOM + "title") or "").strip()
    entries = []
    for e in root.findall(_ATOM + "entry"):
        vtitle = (e.findtext(_ATOM + "title") or "").strip()
        published = e.findtext(_ATOM + "published") or ""
        vid = e.findtext(_YT + "videoId") or ""
        entries.append({"title": vtitle, "published": published, "video_id": vid})
    return title, entries


def _keywords(titles, k=12):
    counter = collections.Counter()
    for t in titles:
        for w in re.findall(r"[^\W\d_]{3,}", t.lower(), flags=re.UNICODE):
            if w not in _STOP:
                counter[w] += 1
    return [w for w, _ in counter.most_common(k)]


def _cadence(entries):
    dates = []
    for e in entries:
        try:
            dates.append(datetime.datetime.fromisoformat(e["published"].replace("Z", "+00:00")))
        except Exception:
            pass
    if len(dates) < 2:
        return None
    span_days = (max(dates) - min(dates)).days or 1
    per_week = round(len(dates) / (span_days / 7.0), 1)
    return {"videos_sampled": len(dates), "span_days": span_days, "per_week": per_week}


def analyze(url, log=lambda m: None):
    cid = resolve_channel_id(url, log)
    log(f"resolved channel id: {cid}")
    title, entries = fetch_recent(cid)
    log(f"channel: {title!r} — {len(entries)} recent uploads from RSS")
    titles = [e["title"] for e in entries]
    avg_words = round(sum(len(t.split()) for t in titles) / max(len(titles), 1), 1)
    profile = {
        "channel_id": cid,
        "channel_title": title,
        "sampled": len(titles),
        "avg_title_words": avg_words,
        "cadence": _cadence(entries),
        "top_keywords": _keywords(titles),
        "sample_titles": titles[:8],
    }
    return profile
