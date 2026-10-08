# Input Provenance, Vintage and Distribution Conditions

**Research vintage:** challenge package based on Overture August 19, 2026 (`2026-08-19.0`). **Access:** fixed Source Cooperative public bucket published by Humane Intelligence/Radiant Earth for this challenge; preflight checked on 2026-10-08.

**Official competition:** https://zindi.world/competitions/bias-bounty-mapping-equity-challenge  
**Package documentation:** https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/README.md  
**Overture attribution:** https://docs.overturemaps.org/attribution/  
**OpenStreetMap contribution attribution:** © OpenStreetMap contributors, Overture Maps Foundation.

For each of five packages (`eastern-ok`, `maricopa-az`, `northern-ca`, `south-central-tx`, `eastern-wa`), the feature-extraction SQL reads exactly eight public challenge resources:

| Role | Public relative key | Purpose |
|---|---|---|
| Sample GEOIDs | `reference/<region>/<region>-sample-submission.csv` | Authoritative inclusion and ordering; only `GEOID` is used |
| Tract geometry | `strata/<region>/<region>-census-tracts.parquet` | CRS-transformed tract geometry, area, perimeter |
| Buildings | `reference/<region>/<region>-overture-buildings.parquet` | Footprint centroids, counts, source composition |
| Roads filtered | `reference/<region>/<region>-overture-roads.parquet` | Classified road lengths |
| Roads unfiltered | `reference/<region>/<region>-overture-roads-unfiltered.parquet` | Road-network context and classes |
| Rail | `reference/<region>/<region>-overture-rail.parquet` | Rail context |
| Infrastructure | `reference/<region>/<region>-overture-infrastructure.parquet` | Infrastructural centroid counts |
| Places | `reference/<region>/<region>-overture-pois.parquet` | Observed POI count, categories and confidence |

Public HTTPS base: `https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/`. The original DuckDB source uses the equivalent anonymous public S3 bucket `s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/`.

**Preflight evidence:** 40/40 public HEAD requests returned HTTP 200 on 2026-10-08; historical frozen samples were hash-verified. HEAD and ETag alone do **not** guarantee immutable source bytes or complete DuckDB body reads. A full independent five-region raw rebuild has not been certified; Northern California's source-to-feature recomputation has.

**Licenses:** challenge package data-sharing terms state CC BY-SA 4.0, with third-party Overture terms continuing to apply. Overture buildings/transportation data may involve the Open Database License (ODbL), while Overture places can be CDLA Permissive 2.0, Apache 2.0 or other source-specific attributions. No assertion is made that these terms are superseded by challenge rules. This repository deliberately excludes raw GeoParquet, raw linked phone records, derived 42-column features, and private validation packets; readers obtain publicly licensed inputs from their original source. Any subsequent redistribution of derived features requires its own legal and attribution review.

**Exclusions:** no removed TIGER/Line, Microsoft footprint, HIFLD facility, CBP establishment, or old organizer gap-target data is loaded. No reconstructed target table, previous withdrawn submission or leaderboard feedback is an input to the scored pipeline. Public documentation of the organizer's reference methodology is contextual only.
