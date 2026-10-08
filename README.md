# Mapping Equity: Reference-Free Coverage Shortfall Audit

**Best Documentation - Zindi Bias Bounty Mapping Equity Challenge (2026)**

**Participant:** `chizzydev250`  
**Associated numerical submission:** `Kmiqz6te`  
**Input snapshot:** 2026-08-19 Overture challenge extracts

## Research approach

This work estimates **relative Overture representation shortfall** from the observed Overture data itself. It does **not** recreate the organizers' withheld TIGER/Microsoft/HIFLD/CBP denominators or their reference gap labels. The estimator predicts typical per-tract observed building, POI and major-road densities from correlated observed Overture context using leave-one-region-out, region-balanced quadratic ridge models. For each component it compares observed density to fitted expected density and combines three bounded shortfalls with equal weights.

**Result lineage:** original V2-2 Overture feature extractor -> frozen V2-21 model functions -> two-column V2-22B score serialization -> Zindi submission `Kmiqz6te`.

The confirmed Zindi-uploaded file contains **9,794** GEOIDs from five public packages. The four principal scored regions contain **9,379** GEOIDs. The remaining 415 are an Eastern Washington supplement; nothing here claims those extra rows contributed to public leaderboard RMSE.

## Reproduce from the challenge data (full pipeline)

Python **3.12**:

```bash
python -m pip install -r requirements.txt
python fetch_samples.py
python src/overture_features.py
python run_scoring.py --output-dir run_output
```

The feature extractor streams remote GeoParquet and performs spatial DuckDB joins. It uses the **original frozen observational SQL** with portable paths. A full five-region raw input rebuild can require considerable time, bandwidth and temporary disk space; it has **not** been executed end-to-end on an independent new machine. Don't run it in a low-disk environment. For a cheaper pilot:

```bash
python src/overture_features.py --region northern-ca
```

That isolated single-region command creates a 591-row feature CSV, **not** a five-region table. It is a feature-extraction check; `run_scoring.py` requires all five regions.

## Reproduce from a verified frozen feature table

If you already have the published-challenge-derived frozen 42-column `V2-2-overture-core-features.csv`, place it in `outputs/`, then:

```bash
python fetch_samples.py
python run_scoring.py --features outputs/V2-2-overture-core-features.csv --strict-frozen-feature-hash --output-dir run_output
```

The historical frozen feature table fingerprint is `0C92ED6B38A5AD78F6406569765FB87AC311D93121D278ACD0AE6B51DBFE90A6`. It is **not redistributed in this source-code-only repository**. `fetch_samples.py` reads only the five public authoritative sample templates and verifies exact historical hashes; it does not read their placeholder score values. The runner emits candidate components, two-column submission and a machine-readable report to a new output directory. Original SHA of the Zindi-downloaded submission: `D6DC4E8DD6C3D94D156049AC2364E289C38EE38E46BF3C1E37107F8F4E0C7C57`.

Cross-environment score reproduction is numerical (tolerance `1e-10`), not necessarily byte-identical. Local rerun checks reproduced all scores to near machine precision; a public-source rebuild in Northern California reproduced 591 feature rows and 23,184 numerical cells to max absolute difference `4.55e-12`. The complete raw five-region rebuild **has not been independently repeated**.

## Read the method

- [Methodology and estimator](docs/METHODOLOGY.md)
- [Data sources, geometry and licenses](docs/DATA_PROVENANCE.md)
- [Reproduction evidence and unresolved qualifications](docs/REPRODUCTION_CERTIFICATE.md)
- [Edge cases, alternative choices and limitations](docs/EDGE_CASES_AND_ALTERNATIVES.md)
- [Original source fingerprints and portability changes](docs/SOURCE_LINEAGE.json)

All model computations use NumPy and Pandas; raw geospatial extraction uses DuckDB and its open-source `httpfs` and `spatial` extensions. No paid service, withdrawn reference layer, hidden target values, or previous leaderboard labels are runtime inputs. The code and narrative are provided openly for competition participants. Input datasets remain governed by their original Zindi and Overture attribution/licensing terms.
