# Sourced Link Completion Pass

This pass turns the Release Vault into a stronger public cross-link surface by harvesting links already present in the repository pages/data and feeding them back into the generated track ecosystem graph.

## Added primary all-links route

Primary all-links URL:

https://ffm.bio/no4km87

This link is now included in:

- `docs/official-links.json`
- `docs/sourced-page-links.json`
- every generated track route
- `release-index.html`
- `release-search.html`
- `index.html`
- JSON-LD `sameAs` output for track pages
- `llms.txt`

## Link sourcing behavior

The generator now scans public source-facing files for outbound links and saves them to:

`docs/sourced-page-links.json`

The scanner intentionally avoids generated track pages and generated index pages so repeated builds do not recursively amplify their own output.

## Rebuild

```bash
python scripts/build_release_crosslink_index.py
python scripts/validate_release_crosslinks.py
python scripts/benchmark_release_vault.py
```

## Current validated coverage

- 104 track routes
- 492 direct/platform/discovery links
- 26,312 ecosystem cross-links
- 216 sourced page links
- A+ release health
- A pipeline benchmark
