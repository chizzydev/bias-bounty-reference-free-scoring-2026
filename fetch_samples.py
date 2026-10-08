#!/usr/bin/env python3
"""Download only public authoritative sample CSVs (no reference targets or labels)."""
from pathlib import Path
from urllib.request import urlopen
import hashlib
import argparse

ROOT=Path(__file__).resolve().parent
EXPECTED={
 'eastern-ok':('56CB40FBA4008D646BC63C62C91E211871459224B3DE8B3A886FF813803FD0D4',1192),
 'eastern-wa':('0E0155D5A5E8EF39DC857C8268669B5FB498D7AC40F0DED782482C67AE5EFEFC',415),
 'maricopa-az':('1640B801D56AB308E68C65583B88CFB9E1555B05A6D0B922EABA22AC09960A31',1593),
 'northern-ca':('F38017B5284667B80B451685FD146388C108E1B30308301289C7A96ECFE60902',591),
 'south-central-tx':('AFA59C0EB30C40BE25CE82098F144447591B79CB9692E669B2F2FE7B7B1EE58E',6003),
}
BASE='https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/reference'
def sha(b):return hashlib.sha256(b).hexdigest().upper()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'inputs/sample');args=parser.parse_args()
 dest=args.output.resolve();dest.mkdir(parents=True,exist_ok=True)
 for name,(digest,rows) in EXPECTED.items():
  target=dest/(name+'-sample-submission.csv')
  if target.exists():
   b=target.read_bytes()
  else:
   url=f'{BASE}/{name}/{name}-sample-submission.csv'
   with urlopen(url,timeout=45) as f:b=f.read()
  if sha(b)!=digest:raise SystemExit(f'FROZEN_SAMPLE_SHA256_MISMATCH:{name} (input data may have been updated)')
  # Do not parse or use placeholder target values; only scored-GEOID membership is consumed downstream.
  if not target.exists():target.write_bytes(b)
  print(f'SAMPLE_SHA256=PASS {name} ROWS_EXPECTED={rows}')
 print('SAMPLE_DOWNLOAD_AND_INTEGRITY=PASS')
if __name__=='__main__':main()
