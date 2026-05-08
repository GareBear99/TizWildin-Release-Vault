#!/usr/bin/env python3
"""Benchmark Release Vault build and validation pipeline."""
from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
steps = [
    ('build_release_crosslink_index', [sys.executable, 'scripts/build_release_crosslink_index.py']),
    ('validate_release_crosslinks', [sys.executable, 'scripts/validate_release_crosslinks.py']),
]
results = []
start_total = time.perf_counter()
for name, cmd in steps:
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    elapsed = time.perf_counter() - start
    results.append({'step': name, 'seconds': round(elapsed, 3), 'returncode': proc.returncode, 'stdout': proc.stdout.strip(), 'stderr': proc.stderr.strip()})
    if proc.returncode:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
health = json.loads((ROOT/'docs/release-health.json').read_text(encoding='utf-8'))
total = time.perf_counter() - start_total
grade = 'A+' if total < 5 and health.get('grade') in {'A+','A'} else 'A' if total < 12 else 'A-' if total < 25 else 'B'
report = {'schema_version':'1.0','pipeline_grade': grade,'total_seconds': round(total,3),'health_grade': health.get('grade'),'metrics': health.get('metrics',{}),'steps': results}
(ROOT/'docs/RELEASE_VAULT_BENCHMARK.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
print(f"BENCHMARK OK: grade {grade}, total {total:.3f}s, release health {health.get('grade')}")
