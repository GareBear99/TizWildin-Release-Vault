#!/usr/bin/env python3
"""Validate generated Release Vault indexes and route coverage."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from urllib.parse import urlparse
ROOT = Path(__file__).resolve().parents[1]

def fail(msg):
    print('VALIDATION ERROR:', msg)
    sys.exit(1)

def load(path):
    p = ROOT / path
    if not p.exists(): fail(f'missing {path}')
    return json.loads(p.read_text(encoding='utf-8'))

idx = load('docs/release-crosslink-index.json')
search = load('docs/release-search-index.json')
health = load('docs/release-health.json')
sourced = load('docs/sourced-page-links.json')
tracks = idx.get('tracks', [])
if not tracks: fail('release index has no tracks')
if search.get('record_count') != len(tracks): fail('search record count does not match track count')
if health.get('metrics', {}).get('tracks') != len(tracks): fail('health track metric does not match track count')
if sourced.get('count', 0) < 1: fail('sourced page link index is empty')
if not any(l.get('url') == 'https://ffm.bio/no4km87' for l in sourced.get('links', [])): fail('FFM Bio link missing from sourced page links')
slugs = set()
for t in tracks:
    title = t.get('title') or ''
    slug = t.get('slug') or ''
    if not title: fail('track missing title')
    if not slug: fail(f'{title} missing slug')
    if slug in slugs: fail(f'duplicate slug: {slug}')
    slugs.add(slug)
    route = ROOT / 'tracks' / slug / 'index.html'
    if not route.exists(): fail(f'{title} missing route page: {route}')
    platform_links = t.get('platform_links', [])
    ecosystem_links = t.get('ecosystem_links', [])
    if len(platform_links) < 3: fail(f'{title} has fewer than 3 platform/discovery links')
    if len(ecosystem_links) < 12: fail(f'{title} has weak ecosystem crosslink coverage')
    if not any(l.get('url') == 'https://ffm.bio/no4km87' for l in platform_links + ecosystem_links):
        fail(f'{title} is missing FFM Bio / all links route')
    for link in platform_links + ecosystem_links:
        url = link.get('url','')
        parsed = urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc:
            fail(f'{title} has invalid URL: {url}')

sitemap = (ROOT/'sitemap.xml').read_text(encoding='utf-8')
for t in tracks:
    needle = f"tracks/{t['slug']}/"
    if needle not in sitemap:
        fail(f'{needle} missing from sitemap')
for required in ['release-index.html','release-search.html','index-health.html','llms.txt','robots.txt','docs/sourced-page-links.json']:
    if not (ROOT/required).exists(): fail(f'missing {required}')

leaks = []
for p in ROOT.rglob('*'):
    if p.is_file() and p.suffix.lower() in {'.html','.md','.txt','.json','.py','.yml','.yaml'}:
        txt = p.read_text(encoding='utf-8', errors='ignore')
        if re.search(r'\b' + 'dar' + 'pa' + r'\b', txt, re.I):
            leaks.append(str(p.relative_to(ROOT)))
if leaks:
    fail('non-public audit branding leaked into public files: ' + ', '.join(leaks[:10]))
print(f"VALIDATION OK: {len(tracks)} tracks, {sum(len(t['platform_links']) for t in tracks)} platform/discovery links, {sum(len(t['ecosystem_links']) for t in tracks)} ecosystem cross-links, {sourced.get('count')} sourced page links, health {health.get('grade')}")
