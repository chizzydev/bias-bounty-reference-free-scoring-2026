# Edge Cases, Alternative Models and Negative Evidence

## Scored geography

- Every GEOID is read as a string preserving 11 digits and any leading zero. Membership is fixed by the five public sample CSVs; polygon file extras do not determine output membership.
- The South-Central Texas polygon inventory includes seven additional zero-land/zero-population water-designated polygon IDs outside the authoritative sample list. They are not silently added to scores.
- The official Maricopa package includes a non-Arizona tract GEOID. Region is determined from official sample membership, not by assuming all region members share an Arizona prefix.
- Empty-population tracts are included if listed in the samples. The model does not filter on population, SVI, CVI or hazard strata.

## Geometric and missing-data cases

- Tracts with no observed Overture buildings or POIs still receive zero observed counts; spatial joins are left-joined to preserve all scored tracts.
- A tract with no observed road network receives zero road context and zero computed road shares. `filtered_road_length_share` is filled with zero for model input when undefined.
- Area conversion is WGS84 to EPSG:5070 equal-area projection. Model density calculations impose a 1e-12 positive area floor; this protects division but is not a scientifically meaningful estimate for a zero-area tract.
- Null source-confidence fields remain missing where source SQL does not define them. During model preparation many declared predictor columns are filled as zero; confidence missingness should not be interpreted as observed zero confidence.
- Spatial joins use centroid-in-tract logic for whole building/road/rail features, with potential bias at boundaries. No network-distance or road clipping claim is made.
- `bounded_shortfall()` returns zero if observed or expected values are undefined / nonfinite or expected density is <=1e-12; this is a conservative modeling convention and not the organizer's reference-definedness logic.
- Final scores must be finite and bounded in [0,1] for each unique GEOID; no NaNs, blanks, rows from non-sample tracts or rounded discrete thresholds are permitted.

## Alternative choices and what is not claimed

- Earlier V2-13 baseline used frozen observed cross-layer quadratic models with ridge=1 for buildings/POIs and ridge=10 for road context. V2-20 evaluated a range of POI expected-density blending weights (0, 0.25, 0.50, 0.75, 1.00). V2-21 froze the 50/50 blend before public leaderboard submission, retaining the same building and road components.
- Do not claim these weights optimize organizer reference RMSE. Their development comparison comes from observational internal checks, not target-score supervision.
- The equal three-way final aggregation was frozen for the submitted model. It differs intentionally from an organizer score that averages only reference-defined components; no evidence is offered that equal weighting is calibrated to hidden targets.
- Historical five-region training includes Eastern Washington as a donor / held-out package. Removing it or restricting the model to four packages would define a *different* model, so the original frozen training and output are preserved even though only four principal regions are described as scored.
- The observed shortfall can be biased by Overture source-provider composition, classification, road completeness or expected-density extrapolation. The numerical audit is not a proof of fairness, clinical risk or disaster-response impact.
