# Track Cross-Link Operations

This vault is now built around generated track routes instead of one static page.

## What gets generated

Running the builder creates:

- `release-index.html` — all track routes in one crawler-friendly index.
- `release-search.html` — client-side search across tracks, statuses, direct links, and ecosystem links.
- `index-health.html` — public health/readiness dashboard.
- `tracks/<track-slug>/index.html` — one canonical route per track.
- `docs/release-crosslink-index.json` — machine-readable track/link graph.
- `docs/release-search-index.json` — machine-readable search index.
- `docs/release-health.json` — route/link/source coverage score.
- `sitemap.xml`, `robots.txt`, and `llms.txt` — crawler/AI discovery files.

## Source data

The builder pulls from the existing vault data files:

- `docs/release-link-matrix.json`
- `docs/soundcloud-monetized-releases.json`
- `docs/distributed-releases.json`
- `docs/youtube-individual-videos.json`
- `docs/facebook-post-index.json`
- `docs/official-links.json`
- `docs/free-sample-packs.json`
- `docs/github-related-repos.json`
- `docs/banner-assets.json`
- `docs/soundcloud-notifications.txt`

## Add another track

Add a track entry to `docs/release-link-matrix.json` or `docs/soundcloud-monetized-releases.json`, then run:

```bash
python scripts/build_release_crosslink_index.py
python scripts/validate_release_crosslinks.py
python scripts/benchmark_release_vault.py
```

The new route, sitemap entry, search record, and ecosystem cross-links will be generated automatically.

## Cross-link rule

Every track route must have:

1. A canonical track page.
2. A sitemap URL.
3. Direct platform/discovery links.
4. Full ecosystem links back to the HUB, SoundCloud, YouTube, Facebook, GitHub, FreeEQ8, Voxel Audio, sample packs, and related public resources.
5. Related-track links so crawler flow does not dead-end.

## Public language rule

Keep public-facing language professional, clear, and creator-owned. Audit style may be strict, but internal labels or agency-style names should not be used in public files.
