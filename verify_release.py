#!/usr/bin/env python3
"""Verify the code-only release is intact (no remote access)."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parent
m=json.loads((root/'docs/FINAL_FILE_MANIFEST.json').read_text())
errors=[]
for relative,meta in m.items():
 p=root/relative
 if not p.is_file():errors.append('MISSING '+relative);continue
 h=hashlib.sha256(p.read_bytes()).hexdigest().upper()
 if h!=meta['sha256']:errors.append('HASH_DRIFT '+relative)
for e in errors:print(e)
if errors:print('RELEASE_INTEGRITY=FAIL');sys.exit(1)
print('RELEASE_INTEGRITY=PASS FILES='+str(len(m)))
