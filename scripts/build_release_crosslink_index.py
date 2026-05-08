#!/usr/bin/env python3
"""Build the TizWildin Release Vault cross-link index.

Reads the vault JSON files plus optional SoundCloud notification text and produces:
- docs/release-crosslink-index.json
- docs/release-search-index.json
- docs/release-health.json
- release-index.html
- release-search.html
- index-health.html
- tracks/<slug>/index.html
- updated sitemap.xml, robots.txt, llms.txt
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, quote_plus

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TRACKS = ROOT / "tracks"
BASE_URL = "https://garebear99.github.io/TizWildin-Release-Vault/"
GENERATOR_VERSION = "1.1.0"

STATUS_RANK = {
    "distribution approved": 5,
    "monetized": 4,
    "distribution rejected": 3,
    "disabled": 2,
    "pending": 1,
    "unknown": 0,
}

DEFAULT_CROSS_LINKS = [
    {"type": "All Links", "label": "TizWildin FFM Bio", "url": "https://ffm.bio/no4km87"},
    {"type": "Hub", "label": "TizWildinEntertainmentHUB", "url": "https://garebear99.github.io/TizWildinEntertainmentHUB/"},
    {"type": "Release Vault", "label": "Release Vault Home", "url": BASE_URL},
    {"type": "SoundCloud", "label": "TizWildin on SoundCloud", "url": "https://soundcloud.com/tizwildin"},
    {"type": "YouTube", "label": "TizWildin YouTube", "url": "https://www.youtube.com/@gfgfvmhj"},
    {"type": "Facebook", "label": "TizWildin Facebook", "url": "https://www.facebook.com/61564485196765"},
    {"type": "GitHub", "label": "GareBear99 GitHub", "url": "https://github.com/GareBear99"},
    {"type": "Plugin", "label": "FreeEQ8", "url": "https://github.com/GareBear99/FreeEQ8"},
    {"type": "Creator Tool", "label": "Voxel Audio", "url": "https://github.com/GareBear99/Voxel_Audio"},
    {"type": "Audio List", "label": "Awesome Audio Plugins Dev", "url": "https://github.com/GareBear99/awesome-audio-plugins-dev"},
    {"type": "Sample Packs", "label": "Free sample packs on HUB", "url": "https://garebear99.github.io/TizWildinEntertainmentHUB/#tizwildin-free-sample-packs"},
]

STOPWORDS = {"the","and","with","from","wip","finalmix","unmastered","nonfinal","single","sample","loop","official","release","mastered","python","music","feat","vip"}


EXCLUDED_LINK_SOURCE_NAMES = {
    "release-crosslink-index.json",
    "release-search-index.json",
    "release-health.json",
    "RELEASE_VAULT_BENCHMARK.json",
    "sitemap.xml",
    "llms.txt",
    "release-index.html",
    "release-search.html",
    "index-health.html",
}


def classify_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "ffm.bio" in host:
        return "All Links"
    if "soundcloud.com" in host:
        return "SoundCloud"
    if "youtube.com" in host or "youtu.be" in host:
        return "YouTube"
    if "facebook.com" in host or "fb.watch" in host:
        return "Facebook"
    if "github.com" in host:
        return "GitHub"
    if "garebear99.github.io" in host:
        return "GitHub Pages"
    if "spotify.com" in host:
        return "Spotify"
    if "apple.com" in host:
        return "Apple Music"
    if "bandcamp.com" in host:
        return "Bandcamp"
    return "Sourced Page Link"


def clean_label(label: str, url: str) -> str:
    label = re.sub(r"\s+", " ", (label or "").strip())
    if not label or len(label) > 90:
        path = urlparse(url).path.strip("/") or urlparse(url).netloc
        label = path.replace("/", " / ")[:90] or url
    return label


def harvest_page_links():
    """Harvest public links from source pages/data so the generated index does not miss existing routes.

    This intentionally skips generated track pages and generated indexes to avoid recursive
    self-amplification. It reads only source-facing pages, markdown, and curated JSON docs.
    """
    candidates = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or ".git" in p.parts:
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("tracks/"):
            continue
        if p.name in EXCLUDED_LINK_SOURCE_NAMES:
            continue
        if p.suffix.lower() not in {".html", ".md", ".json", ".txt"}:
            continue
        if "docs/soundcloud-notification" in rel:
            continue
        candidates.append(p)

    seen = set()
    sourced = []
    url_re = re.compile(r"https?://[^\s\"'<>),]+")
    href_re = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
    md_re = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

    for p in candidates:
        rel = p.relative_to(ROOT).as_posix()
        txt = p.read_text(encoding="utf-8", errors="ignore")
        found = []
        for url, label_html in href_re.findall(txt):
            if url.startswith("http"):
                label = re.sub(r"<[^>]+>", " ", label_html)
                found.append((url, label))
        for label, url in md_re.findall(txt):
            found.append((url, label))
        for url in url_re.findall(txt):
            found.append((url, ""))
        for url, label in found:
            url = url.rstrip(".;]")
            if not url.startswith(("http://", "https://")):
                continue
            key = (rel, url)
            if key in seen:
                continue
            seen.add(key)
            sourced.append({
                "type": classify_url(url),
                "label": clean_label(label, url),
                "url": url,
                "source_file": rel,
            })
    # Also guarantee the top-level fan-link exists even when no source file mentions it yet.
    sourced.append({"type":"All Links", "label":"TizWildin FFM Bio", "url":"https://ffm.bio/no4km87", "source_file":"docs/official-links.json"})
    return merge_links(sourced)


def quote_query(value: str) -> str:
    return quote_plus(value)


def load_json(path: str, default):
    p = ROOT / path
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    s = value.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "track"


def normalize_title(value: str) -> str:
    s = value.lower()
    s = s.replace("_", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    parts = [p for p in s.split() if p not in STOPWORDS]
    return " ".join(parts) or re.sub(r"\s+", " ", s).strip()


def token_set(value: str) -> set[str]:
    return set(normalize_title(value).split())


def merge_links(*link_lists):
    seen = set()
    out = []
    for links in link_lists:
        for link in links or []:
            if isinstance(link, dict):
                url = link.get("url") or link.get("href") or ""
                label = link.get("label") or link.get("title") or link.get("type") or url
                ltype = link.get("type") or link.get("platform") or "Link"
            elif isinstance(link, (list, tuple)) and len(link) >= 2:
                ltype, url = "Link", str(link[1])
                label = str(link[0])
            else:
                continue
            if not url or not str(url).startswith(("http://", "https://")):
                continue
            key = (url.strip(), label.strip())
            if key in seen:
                continue
            seen.add(key)
            out.append({"type": str(ltype), "label": str(label), "url": str(url)})
    return out


def parse_notifications():
    candidates = [Path("/mnt/data/Pasted text(30).txt"), ROOT / "docs" / "soundcloud-notifications.txt"]
    text = ""
    source_path = None
    for p in candidates:
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="ignore")
            source_path = str(p)
            break
    events = []
    if not text:
        return events, None
    pattern = re.compile(r"Your (track|Distribution release) '(.+?)' (is monetizing|is disabled for monetization|has been approved for monetization|has been rejected for monetization)\s*\n(\d{1,2} \w+ 2026)", re.S)
    for kind, title, action, date in pattern.findall(text):
        title = title.strip()
        action = action.strip()
        if "approved" in action:
            status = "Distribution Approved"
        elif "rejected" in action:
            status = "Distribution Rejected"
        elif "disabled" in action:
            status = "Disabled"
        elif "monetizing" in action:
            status = "Monetized"
        else:
            status = "Unknown"
        events.append({"title": title, "kind": kind, "action": action, "status": status, "date": date})
    return events, source_path


def status_key(status: str) -> str:
    s = status.lower()
    if "approved" in s:
        return "distribution approved"
    if "rejected" in s:
        return "distribution rejected"
    if "disabled" in s:
        return "disabled"
    if "monet" in s:
        return "monetized"
    if "pending" in s or "submitted" in s:
        return "pending"
    return "unknown"


def better_status(a: str, b: str) -> str:
    return a if STATUS_RANK.get(status_key(a),0) >= STATUS_RANK.get(status_key(b),0) else b


def find_best_track_key(title: str, keys: list[str]) -> str | None:
    nt = normalize_title(title)
    if nt in keys:
        return nt
    ts = token_set(title)
    if not ts:
        return None
    best = None
    best_score = 0.0
    for key in keys:
        kt = set(key.split())
        if not kt:
            continue
        inter = len(ts & kt)
        union = len(ts | kt)
        score = inter / union if union else 0
        if score > best_score:
            best_score = score
            best = key
    return best if best_score >= 0.45 else None


def read_all_source_files():
    files = []
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            rel = p.relative_to(ROOT).as_posix()
            try:
                size = p.stat().st_size
                text = p.read_text(encoding="utf-8", errors="ignore") if size < 1_000_000 and p.suffix.lower() not in {".jpg",".jpeg",".png",".gif",".webp",".zip"} else ""
                files.append({"path": rel, "size": size, "lines": text.count("\n") + (1 if text else 0)})
            except Exception:
                files.append({"path": rel, "size": p.stat().st_size, "lines": 0})
    return files


def html_page(title: str, description: str, body: str, canonical: str, image: str = "assets/banners/tizwildin-entertainment-waveform-banner.jpg", extra_head: str = "") -> str:
    img_url = image if image.startswith("http") else BASE_URL + image.lstrip("/")
    safe_title = html.escape(title)
    safe_desc = html.escape(description)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{safe_title}</title>
<meta name=\"description\" content=\"{safe_desc}\">
<meta name=\"robots\" content=\"index, follow, max-image-preview:large\">
<link rel=\"canonical\" href=\"{canonical}\">
<link rel=\"stylesheet\" href=\"{relative_css(canonical)}assets/style.css\">
<meta property=\"og:type\" content=\"website\">
<meta property=\"og:title\" content=\"{safe_title}\">
<meta property=\"og:description\" content=\"{safe_desc}\">
<meta property=\"og:url\" content=\"{canonical}\">
<meta property=\"og:image\" content=\"{img_url}\">
<meta name=\"twitter:card\" content=\"summary_large_image\">
<meta name=\"twitter:title\" content=\"{safe_title}\">
<meta name=\"twitter:description\" content=\"{safe_desc}\">
<meta name=\"twitter:image\" content=\"{img_url}\">
{extra_head}
</head>
<body>
<div class=\"wrap\">
{body}
</div>
</body>
</html>
"""


def relative_css(canonical: str) -> str:
    # Track pages are under /tracks/<slug>/ and need ../../
    if "/tracks/" in canonical:
        return "../../"
    return ""


def link_buttons(links):
    if not links:
        return "<p class='muted'>No direct links recorded yet.</p>"
    return "\n".join(f"<a class='mini-link' href='{html.escape(l['url'])}'>{html.escape(l['type'])}: {html.escape(l['label'])}</a>" for l in links)


def build():
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    matrix = load_json("docs/release-link-matrix.json", [])
    monetized = load_json("docs/soundcloud-monetized-releases.json", [])
    distributed = load_json("docs/distributed-releases.json", [])
    youtube = load_json("docs/youtube-individual-videos.json", [])
    fb = load_json("docs/facebook-post-index.json", [])
    official = load_json("docs/official-links.json", {})
    packs = load_json("docs/free-sample-packs.json", [])
    repos = load_json("docs/github-related-repos.json", [])
    banners = load_json("docs/banner-assets.json", {})
    sourced_page_links = harvest_page_links()
    write_json(DOCS / "sourced-page-links.json", {"schema_version":"1.0", "generated_at": generated_at, "count": len(sourced_page_links), "links": sourced_page_links})
    notifications, notification_source = parse_notifications()

    tracks = {}

    def ensure(title):
        key = normalize_title(title)
        if key not in tracks:
            tracks[key] = {
                "title": title,
                "slug": slugify(title),
                "status": "Unknown",
                "statuses": [],
                "links": [],
                "platform_links": [],
                "ecosystem_links": [],
                "related_tracks": [],
                "banner": "",
                "sources": [],
                "notifications": [],
                "seo_keywords": [],
            }
        return tracks[key]

    # Matrix and monetized sources.
    for src_name, items in [("release-link-matrix", matrix), ("soundcloud-monetized-releases", monetized)]:
        for item in items:
            t = ensure(item.get("title", "Untitled"))
            t["status"] = better_status(t["status"], item.get("status", "Unknown"))
            t["statuses"].append({"source": src_name, "status": item.get("status", "Unknown")})
            t["links"] = merge_links(t["links"], item.get("links", []))
            if item.get("soundcloud"):
                t["links"] = merge_links(t["links"], [{"type":"SoundCloud","label":"Track","url":item["soundcloud"]}])
            if item.get("banner"):
                t["banner"] = item["banner"]
            t["sources"].append(src_name)

    # Distributed releases.
    for item in distributed:
        t = ensure(item.get("title", "Untitled"))
        t["status"] = better_status(t["status"], item.get("status", "Pending"))
        t["statuses"].append({"source":"distributed-releases", "status": item.get("status", "Pending")})
        if item.get("source"):
            t["links"] = merge_links(t["links"], [{"type":"SoundCloud","label":"Distribution source","url":item["source"]}])
        if item.get("banner"):
            t["banner"] = item["banner"]
        t["sources"].append("distributed-releases")

    keys = list(tracks.keys())
    # YouTube cross links.
    for item in youtube:
        track_name = item.get("track") or item.get("title", "")
        key = find_best_track_key(track_name, keys)
        if key is None:
            t = ensure(track_name)
            keys = list(tracks.keys())
        else:
            t = tracks[key]
        t["links"] = merge_links(t["links"], [{"type":"YouTube","label":item.get("title", "Video"),"url":item.get("url","")}])
        t["sources"].append("youtube-individual-videos")

    # Facebook links.
    for item in fb:
        track_name = item.get("track") or item.get("title", "")
        if track_name.lower() == "page":
            continue
        key = find_best_track_key(track_name, list(tracks.keys()))
        if key:
            t = tracks[key]
            t["links"] = merge_links(t["links"], [{"type":"Facebook","label":item.get("title", "Post"),"url":item.get("url","")}])
            t["sources"].append("facebook-post-index")

    # Notification statuses.
    keys = list(tracks.keys())
    for ev in notifications:
        key = find_best_track_key(ev["title"], keys)
        if key is None:
            t = ensure(ev["title"])
            keys = list(tracks.keys())
        else:
            t = tracks[key]
        t["status"] = better_status(t["status"], ev["status"])
        t["statuses"].append({"source":"soundcloud-notification-export","status": ev["status"], "date": ev["date"]})
        t["notifications"].append(ev)
        if "soundcloud-notification-export" not in t["sources"]:
            t["sources"].append("soundcloud-notification-export")

    # Ensure slugs unique.
    slug_counts = Counter()
    for t in tracks.values():
        base = t["slug"]
        slug_counts[base] += 1
        if slug_counts[base] > 1:
            t["slug"] = f"{base}-{slug_counts[base]}"

    # Ecosystem links per track.
    official_links = [{"type":"Official", "label":k, "url":v} for k,v in official.items() if isinstance(v,str) and v.startswith("http")]
    repo_links = [{"type":"GitHub Repo", "label":r[0], "url":r[1]} for r in repos if isinstance(r, list) and len(r) >= 2]
    pack_links = []
    for p in packs:
        if p.get("repo"):
            pack_links.append({"type":"Sample Pack", "label":p.get("name","Pack"), "url":p["repo"]})
        if p.get("hub"):
            pack_links.append({"type":"Sample Pack Hub", "label":p.get("name","Pack") + " on HUB", "url":p["hub"]})
    global_cross = merge_links(DEFAULT_CROSS_LINKS, official_links, repo_links, pack_links, sourced_page_links)

    all_tracks = list(tracks.values())
    for t in all_tracks:
        query = quote_query("TizWildin " + t["title"])
        generated_discovery_links = [
            {"type":"All Links", "label":"TizWildin FFM Bio / all official links", "url":"https://ffm.bio/no4km87"},
            {"type":"SoundCloud Search", "label":"Search this track on SoundCloud", "url":"https://soundcloud.com/search?q=" + query},
            {"type":"YouTube Search", "label":"Search this track on YouTube", "url":"https://www.youtube.com/results?search_query=" + query},
            {"type":"Google Search", "label":"Search this release across the web", "url":"https://www.google.com/search?q=" + query},
        ]
        t["platform_links"] = merge_links(t["links"], generated_discovery_links)
        t["ecosystem_links"] = merge_links(global_cross)
        words = sorted(token_set(t["title"]))[:8]
        t["seo_keywords"] = ["TizWildin", "GareBearProductionz", "electronic music", "SoundCloud", "music visualizer"] + words
        # Related by token overlap or same status.
        related = []
        ts = token_set(t["title"])
        for other in all_tracks:
            if other is t:
                continue
            overlap = len(ts & token_set(other["title"]))
            same_status = status_key(other["status"]) == status_key(t["status"])
            score = overlap * 3 + (1 if same_status else 0)
            if score > 0:
                related.append((score, other["title"], other["slug"], other["status"]))
        related = sorted(related, reverse=True)[:6]
        t["related_tracks"] = [{"title":r[1], "slug":r[2], "status":r[3], "url":f"tracks/{r[2]}/"} for r in related]

    all_tracks = sorted(all_tracks, key=lambda x: (status_key(x["status"]), x["title"].lower()), reverse=True)
    stats = Counter(status_key(t["status"]) for t in all_tracks)

    # Track pages.
    TRACKS.mkdir(exist_ok=True)
    for t in all_tracks:
        page_dir = TRACKS / t["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        canonical = BASE_URL + f"tracks/{t['slug']}/"
        image = t["banner"] or "assets/banners/tizwildin-entertainment-waveform-banner.jpg"
        desc = f"{t['title']} by TizWildin / GareBearProductionz: release-vault status, platform links, SoundCloud/YouTube/Facebook routes, sample-pack routes, and ecosystem cross-links."
        jsonld = {
            "@context":"https://schema.org",
            "@type":"MusicRecording",
            "name": t["title"],
            "byArtist": {"@type":"MusicGroup", "name":"TizWildin", "url": BASE_URL},
            "url": canonical,
            "image": BASE_URL + image if image and not image.startswith("http") else image,
            "isAccessibleForFree": True,
            "sameAs": [l["url"] for l in t["platform_links"][:10]],
            "keywords": ", ".join(t["seo_keywords"]),
        }
        notif_rows = "".join(f"<tr><td>{html.escape(n['date'])}</td><td>{html.escape(n['kind'])}</td><td>{html.escape(n['status'])}</td><td>{html.escape(n['action'])}</td></tr>" for n in t["notifications"])
        notif_table = f"<table><tr><th>Date</th><th>Type</th><th>Status</th><th>Notification</th></tr>{notif_rows}</table>" if notif_rows else "<p class='muted'>No exported notification row attached yet.</p>"
        related_html = "".join(f"<a class='mini-link' href='../../tracks/{html.escape(r['slug'])}/'>{html.escape(r['title'])}</a>" for r in t["related_tracks"])
        body = f"""
<section class='hero'>
  <p class='meta'>TizWildin Release Vault / Track Route</p>
  <h1>{html.escape(t['title'])}</h1>
  <p>{html.escape(desc)}</p>
  <div class='nav'>
    <a class='btn hot' href='../../release-index.html'>Release Index</a>
    <a class='btn' href='../../release-search.html'>Search Vault</a>
    <a class='btn' href='../../'>Vault Home</a>
    <a class='btn' href='https://ffm.bio/no4km87'>All Links / FFM Bio</a>
    <a class='btn' href='https://garebear99.github.io/TizWildinEntertainmentHUB/'>Main HUB</a>
  </div>
</section>
<section class='section grid'>
  <div class='panel card'><div class='body'><h2>Status</h2><p><span class='badge'>{html.escape(t['status'])}</span></p><p class='muted'>Sources: {html.escape(', '.join(sorted(set(t['sources']))))}</p></div></div>
  <div class='panel card'><div class='body'><h2>Direct Track Links</h2>{link_buttons(t['platform_links'])}</div></div>
</section>
<section class='section panel card'><div class='body'><h2>Full Ecosystem Cross-Links</h2><p class='muted'>Every track route links outward to the complete public-facing TizWildin stack so discovery does not dead-end.</p>{link_buttons(t['ecosystem_links'])}</div></section>
<section class='section panel card'><div class='body'><h2>Notification / Monetization Evidence</h2>{notif_table}</div></section>
<section class='section panel card'><div class='body'><h2>Related Track Routes</h2>{related_html or '<p class="muted">No related track routes computed yet.</p>'}</div></section>
<footer class='footer'>Generated by Release Vault cross-link index v{GENERATOR_VERSION}. Add or update JSON data, rerun the builder, and the track route refreshes automatically.</footer>
"""
        page_html = html_page(f"{t['title']} | TizWildin Release Vault", desc, body, canonical, image, f"<script type='application/ld+json'>{html.escape(json.dumps(jsonld, ensure_ascii=False))}</script>")
        (page_dir / "index.html").write_text(page_html, encoding="utf-8")

    # Release index page.
    cards = []
    for t in all_tracks:
        image = t["banner"] or "assets/banners/tizwildin-entertainment-waveform-banner.jpg"
        cards.append(f"<article class='card'><a href='tracks/{html.escape(t['slug'])}/'><img src='{html.escape(image)}' alt=''></a><div class='body'><h3><a href='tracks/{html.escape(t['slug'])}/'>{html.escape(t['title'])}</a></h3><p><span class='badge'>{html.escape(t['status'])}</span></p><p class='muted'>{len(t['platform_links'])} direct links · {len(t['ecosystem_links'])} ecosystem links · {len(t['related_tracks'])} related tracks</p></div></article>")
    status_bits = " ".join(f"<span class='badge'>{html.escape(k)}: {v}</span>" for k,v in sorted(stats.items()))
    release_body = f"""
<section class='hero'>
  <p class='meta'>Queryable Track Index</p>
  <h1>TizWildin Release Cross-Link Index</h1>
  <p>Generated public index for every known track/release route, direct platform links, SoundCloud notification status, YouTube/Facebook routes, banners, sample-pack routes, and ecosystem cross-links.</p>
  <div class='nav'><a class='btn hot' href='release-search.html'>Search Releases</a><a class='btn' href='index-health.html'>Index Health</a><a class='btn' href='https://ffm.bio/no4km87'>All Links / FFM Bio</a><a class='btn' href='./'>Vault Home</a><a class='btn' href='https://garebear99.github.io/TizWildinEntertainmentHUB/'>Main HUB</a></div>
</section>
<section class='section panel card'><div class='body'><h2>Coverage</h2><p>{status_bits}</p><p class='muted'>{len(all_tracks)} track routes generated. {sum(len(t['platform_links']) for t in all_tracks)} direct platform links. {sum(len(t['ecosystem_links']) for t in all_tracks)} ecosystem cross-links.</p></div></section>
<section class='section grid'>{''.join(cards)}</section>
"""
    (ROOT / "release-index.html").write_text(html_page("TizWildin Release Cross-Link Index", "Search-indexed TizWildin track routes with SoundCloud, YouTube, Facebook, GitHub, HUB, plugin, and sample-pack cross-links.", release_body, BASE_URL + "release-index.html"), encoding="utf-8")

    # Search page.
    search_body = """
<section class='hero'><p class='meta'>Release Vault Search</p><h1>Search TizWildin Releases</h1><p>Client-side search over track titles, statuses, platform links, and ecosystem cross-links.</p><div class='nav'><a class='btn' href='release-index.html'>Release Index</a><a class='btn' href='https://ffm.bio/no4km87'>All Links / FFM Bio</a><a class='btn' href='./'>Vault Home</a></div></section>
<section class='section panel card'><div class='body'><input id='q' placeholder='Search tracks, links, statuses, YouTube, SoundCloud, sample packs...' style='width:100%;padding:14px;border-radius:14px;border:1px solid var(--line);background:#0008;color:#fff;font-size:1rem'><div id='results' class='section grid'></div></div></section>
<script>
const results = document.getElementById('results');
const q = document.getElementById('q');
function card(r){return `<article class="card"><div class="body"><h3><a href="${r.url}">${r.title}</a></h3><p><span class="badge">${r.status}</span></p><p class="muted">${r.summary}</p><p>${r.links.slice(0,6).map(l=>`<a class="mini-link" href="${l.url}">${l.type}: ${l.label}</a>`).join('')}</p></div></article>`}
fetch('docs/release-search-index.json').then(r=>r.json()).then(data=>{
  function run(){const term=q.value.toLowerCase().trim(); const rows=data.records.filter(r=>!term || r.search_text.includes(term)).slice(0,80); results.innerHTML=rows.map(card).join('') || '<p class="muted">No results.</p>';}
  q.addEventListener('input', run); run();
});
</script>
"""
    (ROOT / "release-search.html").write_text(html_page("Search TizWildin Release Vault", "Search TizWildin tracks, platform links, sample-pack links, and ecosystem routes.", search_body, BASE_URL + "release-search.html"), encoding="utf-8")

    # JSON outputs.
    release_index = {
        "schema_version": "1.0",
        "generator": "scripts/build_release_crosslink_index.py",
        "generator_version": GENERATOR_VERSION,
        "generated_at": generated_at,
        "base_url": BASE_URL,
        "notification_source": notification_source,
        "summary": {
            "track_count": len(all_tracks),
            "status_counts": dict(stats),
            "direct_link_count": sum(len(t["platform_links"]) for t in all_tracks),
            "ecosystem_cross_link_count": sum(len(t["ecosystem_links"]) for t in all_tracks),
            "notification_event_count": len(notifications),
            "sourced_page_link_count": len(sourced_page_links),
        },
        "tracks": all_tracks,
    }
    write_json(DOCS / "release-crosslink-index.json", release_index)

    records = []
    for t in all_tracks:
        links = merge_links(t["platform_links"], t["ecosystem_links"])
        text = " ".join([t["title"], t["status"], " ".join(t["seo_keywords"]), " ".join(l["label"] + " " + l["type"] + " " + l["url"] for l in links)]).lower()
        records.append({"title": t["title"], "status": t["status"], "url": f"tracks/{t['slug']}/", "summary": f"{len(t['platform_links'])} direct links, {len(t['ecosystem_links'])} ecosystem cross-links", "links": links, "search_text": text})
    write_json(DOCS / "release-search-index.json", {"schema_version":"1.0", "generated_at":generated_at, "record_count": len(records), "records": records})

    source_files = read_all_source_files()
    score = 100
    warnings = []
    missing_direct = [t["title"] for t in all_tracks if not t["platform_links"]]
    if missing_direct:
        score -= min(25, len(missing_direct))
        warnings.append(f"{len(missing_direct)} tracks have no direct platform-specific links yet.")
    if len(all_tracks) < 100:
        score -= 3
        warnings.append("Track count is under 100; verify against SoundCloud if more public tracks should be imported.")
    grade = "A+" if score >= 97 else "A" if score >= 92 else "A-" if score >= 87 else "B+" if score >= 82 else "B"
    health = {
        "schema_version":"1.0",
        "generated_at":generated_at,
        "grade": grade,
        "score": max(score,0),
        "warnings": warnings,
        "metrics": {
            "tracks": len(all_tracks),
            "track_pages": len(list(TRACKS.glob("*/index.html"))),
            "direct_links": sum(len(t["platform_links"]) for t in all_tracks),
            "ecosystem_cross_links": sum(len(t["ecosystem_links"]) for t in all_tracks),
            "notification_events": len(notifications),
            "sourced_page_links": len(sourced_page_links),
            "source_files_audited": len(source_files),
            "source_lines_audited": sum(f["lines"] for f in source_files),
        },
        "source_files": source_files,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(DOCS / "release-health.json", health)
    health_body = f"""
<section class='hero'><p class='meta'>Release Vault Health</p><h1>Index Health: {html.escape(grade)}</h1><p>Score {health['score']}/100. Generated {html.escape(generated_at)}.</p><div class='nav'><a class='btn' href='release-index.html'>Release Index</a><a class='btn' href='release-search.html'>Search</a></div></section>
<section class='section grid'>
<div class='card'><div class='body'><h2>{len(all_tracks)}</h2><p class='muted'>Track routes</p></div></div>
<div class='card'><div class='body'><h2>{sum(len(t['platform_links']) for t in all_tracks)}</h2><p class='muted'>Direct links</p></div></div>
<div class='card'><div class='body'><h2>{sum(len(t['ecosystem_links']) for t in all_tracks)}</h2><p class='muted'>Ecosystem cross-links</p></div></div>
<div class='card'><div class='body'><h2>{len(notifications)}</h2><p class='muted'>Notification events imported</p></div></div>
</section>
<section class='section panel card'><div class='body'><h2>Warnings</h2>{''.join(f'<p class="muted">{html.escape(w)}</p>' for w in warnings) or '<p class="muted">No critical warnings.</p>'}</div></section>
"""
    (ROOT / "index-health.html").write_text(html_page("TizWildin Release Vault Index Health", "Release Vault index health, route coverage, link coverage, and source-audit metrics.", health_body, BASE_URL + "index-health.html"), encoding="utf-8")

    # sitemap, robots, llms.
    urls = [BASE_URL, BASE_URL + "release-index.html", BASE_URL + "release-search.html", BASE_URL + "index-health.html"]
    urls += [BASE_URL + f"tracks/{t['slug']}/" for t in all_tracks]
    sitemap = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" + "\n".join(f"  <url><loc>{html.escape(u)}</loc></url>" for u in urls) + "\n</urlset>\n"
    (ROOT / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (ROOT / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://garebear99.github.io/TizWildin-Release-Vault/sitemap.xml\n", encoding="utf-8")
    llms = ["# TizWildin Release Vault", "", "Public release, track, and ecosystem cross-link index for TizWildin / GareBearProductionz.", "", "## Key indexes", "- release-index.html", "- release-search.html", "- docs/release-crosslink-index.json", "- docs/release-search-index.json", "- docs/release-health.json", "- docs/sourced-page-links.json", "- https://ffm.bio/no4km87", "", "## Track routes"]
    llms += [f"- {t['title']}: tracks/{t['slug']}/" for t in all_tracks]
    (ROOT / "llms.txt").write_text("\n".join(llms) + "\n", encoding="utf-8")

    # Patch home page nav non-destructively.
    index = ROOT / "index.html"
    if index.exists():
        text = index.read_text(encoding="utf-8", errors="ignore")
        block = """<a class=\"btn hot\" href=\"release-index.html\">Release Cross-Link Index</a>
<a class=\"btn\" href=\"release-search.html\">Search Releases</a>
<a class=\"btn\" href=\"index-health.html\">Index Health</a>"""
        if "Release Cross-Link Index" not in text:
            text = text.replace("<div class=\"nav\">", "<div class=\"nav\">\n" + block + "\n", 1)
            index.write_text(text, encoding="utf-8")

    print(f"Built release vault cross-link index: {len(all_tracks)} tracks, {len(urls)} sitemap URLs, {sum(len(t['platform_links']) for t in all_tracks)} direct links, {sum(len(t['ecosystem_links']) for t in all_tracks)} ecosystem cross-links in {time.perf_counter()-started:.3f}s")

if __name__ == "__main__":
    build()
