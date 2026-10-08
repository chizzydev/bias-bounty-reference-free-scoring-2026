# Reproduction Certificate - Frozen Model and Public Raw-Source Pilot

**Date of observed tests:** 8 October 2026. **Subject:** Zindi scored submission `Kmiqz6te`, V2-21 alpha50 model / V2-22B serializer.

| Evidence layer | Observed result | Qualification |
|---|---|---|
| Original source and artifact identity | 30/30 packaged DOC-P1 source files match recorded SHA-256 | Existing historical artifact integrity only |
| Exact original Zindi download | V2-22B historical CSV SHA `D6DC4E8DD6C3D94D156049AC2364E289C38EE38E46BF3C1E37107F8F4E0C7C57`, 9,794 GEOIDs | Confirms what was uploaded; fifth package not asserted scored |
| Windows frozen-feature replay | Original V2-21 model max delta `9.97465998686664e-17`; original submission max delta `5.82867087928207e-16` | PASS numerical, `BYTE_IDENTICAL_SUBMISSION=FALSE` |
| Separate Python/Linux frozen-feature replay | Max final composite delta approximately `1.73e-12` | PASS at 1e-10 tolerance; byte stream differs |
| Portable private capsule on Windows | 18/18 fingerprints; model and submitted-score replay PASS | Uses verified frozen derived-feature table; not raw GeoParquet |
| 40-file upstream availability | 40/40 HTTP HEAD 200; local original-source hashes 9/9 PASS; DuckDB 1.5.4 | Preflight only; does not certify body reads |
| Northern California raw features | 591 rows, 23,184 numerical cells, max absolute delta `4.54747350886e-12` | PASS isolated source->feature, original project untouched |
| Full five-region raw-to-feature-to-submission rebuild | **NOT TESTED** | Cannot claim full independent end-to-end reproduction |

## Interpretations

The numerical model is deterministic given its input table, although different NumPy BLAS/Pandas serialization may change low-order digits and therefore CSV SHA-256 bytes. The historical submission SHA is a fixed-identity check, not the cross-platform pass criterion. Fresh predictions are checked to tolerance 1e-10.

The Northern California pilot exercised the **original observational SQL** with only workspace and one-region scope adapted. Building, POI, infrastructure, filtered roads, unfiltered roads and rail stages all completed. Its per-field comparison against the corresponding frozen rows passed. This supports portability of one geographic slice; it is **not** evidence that all five regions have been freshly rebuilt.

The full raw feature builder uses DuckDB `httpfs` and `spatial` extensions, two threads and 4 GB configured memory limit. Geospatial joins can use substantial spill disk space, especially South-Central Texas. The advertised public 40-file sum was approximately 4.22 GiB at preflight; not a promise about bytes streamed by DuckDB. Use a large scratch disk before executing the all-region script.

## Responsible claim boundaries

- The predictions are a **reference-free proxy** and must not be described as recovering omitted official denominator counts or benchmark reference scores.
- Samples define scored tract membership, not target labels. The submission file contains 9,794 five-package rows, but the four principal scored packages total 9,379.
- One regional raw-source reproduction and a complete frozen-feature model replay are different tests. Neither is a full cross-machine raw-to-final-score rerun.
- Original SQL assigns whole road-segment lengths using centroid membership; boundary bias remains a limitation.
- Redistribution of original public challenge files and derived feature tables is not implied by code publication.
