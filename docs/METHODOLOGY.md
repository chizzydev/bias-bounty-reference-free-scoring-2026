# Methodology - Frozen V2-21 Overture-Only Reference-Free Shortfall Estimator

## Scientific question

We cannot observe the competition's withheld reference denominators. Rather than substitute prohibited copies of removed layers, we estimate whether an observed Overture feature density is unexpectedly low given other **observed** Overture context. These are bounded self-supervised proxies, **not** reconstructions of the organizer's road, building or facility-gap definitions.

## Scored universe and unit of analysis

The unit is a 2010/2020 Census tract GEOID as supplied by the fixed challenge CSVs. Source packages: Eastern Oklahoma 1,192; Maricopa 1,593 (including one NM tract within the official package); Northern California 591; South-Central Texas 6,003. These four primary evaluated packages have 9,379 GEOIDs. An Eastern Washington supplement contributes 415 additional submitted GEOIDs, for a historical 9,794-row output; the fifth package is not asserted to affect RMSE. GEOIDs are kept as eleven-character strings; the official sample ID list, **not all tract polygons**, determines membership. No population filtering is applied.

## Observed features and GIS contract

The original V2-2 SQL reads only organizer-provided August 2026 Overture buildings, POIs, filtered and unfiltered roads, rail and infrastructure, plus study tract geometry and public sample GEOID membership. It transforms geometries from EPSG:4326 to EPSG:5070 for area, perimeter and length calculations, using explicit `always_xy`. BBox predicates narrow spatial joins followed by exact spatial predicates. Buildings and infrastructure are assigned by centroid; POIs use point-in-tract intersection; line features are assigned by centroid and count their entire length to that tract (not clipped at boundaries). This can bias road density in narrow/border tracts and is openly documented, not retroactively corrected.

Per-tract attributes include building count, number and entropy of source datasets, reported confidence and source concentrations, POI count and category diversity, infrastructure count, road length by class, major/minor context, filtered and unfiltered road lengths, rail length, and tract area/perimeter. Density features divide by tract area in km². Missing feature counts default to zero where the SQL coalesces them, while missing confidence/stats remain null where original source logic leaves them undefined. In the model, area uses a `1e-12` denominator lower bound; model predictors use declared `fillna(0)` transforms, not external reference population.

## Statistical model

For each held-out study package, fit expected observed densities on all other packages, with region-balanced weights inversely proportional to donor row counts. A ridge regression with standardized design, non-penalized intercept and quadratic terms (squares and pairwise interactions) predicts `log1p(density)`. The fitting uses observed Overture density as the target, **never the organizer's hidden reference gap score**. Models are refitted within each held-out region fold, using frozen hyperparameters and no stochastic sampling.

| Component | Observed quantity | Predictors | Ridge |
|---|---|---|---:|
| Building | building count/km² | POI, all-road, infrastructure and rail densities, area; quadratic interactions | 1 |
| POI base | POI count/km² | Buildings, all roads, infrastructure, rail, area; quadratic interactions | 1 |
| POI augmented head | POI count/km² | Same quadratic base plus observed road-class proportions | 100 |
| Road | major highway length/km² | Internal minor-network, segment, service/track/active/living-street density, road class and area; quadratic interactions | 10 |

The **POI expected log-density** is the 50/50 average of POI-base and augmented-head model predictions. This is a blend *before* back-transform and shortfall calculation; it is not a post-hoc blend of shortfall scores.

For observed density \(o\) and predicted expected log-density \(p\), set \(e=\max(0,\exp(p)-1)\). The shortfall is \(s=1-\min(1,\max(0,o/e))\) for finite \(o,e\) and \(e>10^{-12}\); otherwise \(s=0\). Scores are clamped to [0,1]. The final coverage shortfall proxy is an **equal arithmetic mean** of building, 50/50 POI, and major-road shortfalls. Unlike the organizer's reference-definedness weighted mean, this proxy always has three defined components with conservative `0` fallbacks. It may understate deficits in cases where a reference-based component would be undefined.

## Why this model, not the organizer's target formula?

The public gap-formula narrative is useful context, but the removed reference files are not permitted runtime data. We therefore estimate Overture-internal abnormal low density, and explicitly decline claims of denominator recovery, road transport routing effects or validated safety outcomes. The model has been evaluated with leave-one-region-out internal checks; these measure consistency of observed Overture density prediction, **not** how accurately it predicts unavailable reference labels.

## Output and lineage

The runner produces `GEOID,coverage_gap_score`, exactly one finite [0,1] value per official package GEOID in sample-template order, and writes `REPORT.json` with its hashes. It reads no placeholder target columns for training. Frozen original V2-21 science is retained in `src/v2_21_frozen_model.py` (portable workspace-root change only). The original historical V2-13 and V2-20 explorations are not required to numerically compute the final frozen formula. See `docs/SOURCE_LINEAGE.json` for historical source file SHA-256 and modifications.
