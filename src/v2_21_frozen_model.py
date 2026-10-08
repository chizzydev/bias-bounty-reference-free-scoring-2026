from __future__ import annotations

from pathlib import Path
import hashlib
import itertools
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURES_IN = ROOT / "outputs" / "V2-2-overture-core-features.csv"
V213_IN = ROOT / "outputs" / "V2-13-full-quadratic-reference-free-model.csv"
V220_IN = ROOT / "outputs" / "V2-20-poi-roadmix-shrinkage-path.csv"

OUT = ROOT / "outputs"
INSPECT = ROOT / "inspections"

REPORT = INSPECT / "V2-21-report.txt"
REGION_AUDIT = INSPECT / "V2-21-region-audit.csv"
INFLUENCE = INSPECT / "V2-21-component-influence.csv"
BASELINE_CMP = INSPECT / "V2-21-vs-v2-13.csv"
MANIFEST = INSPECT / "V2-21-release-manifest.txt"
OUTFILE = OUT / "V2-21-alpha50-reference-free-candidate.csv"

EXPECTED_ROWS = 9794
EXPECTED_REGIONS = {
    "eastern-ok": 1192,
    "maricopa-az": 1593,
    "northern-ca": 591,
    "south-central-tx": 6003,
    "eastern-wa": 415,
}

ALPHA = 0.50

BASE_BUILD = [
    "log_poi_density",
    "log_road_all_density",
    "log_infra_density",
    "log_rail_density",
    "log_area",
]

BASE_POI = [
    "log_building_density",
    "log_road_all_density",
    "log_infra_density",
    "log_rail_density",
    "log_area",
]

ROAD_PRED = [
    "log_minor_context_density",
    "log_segment_density",
    "log_service_density",
    "log_track_density",
    "log_active_density",
    "log_living_street_density",
    "log_class_count",
    "log_area",
]

ROAD_MIX = [
    "road_motorway_share",
    "road_trunk_share",
    "road_primary_share",
    "road_secondary_share",
    "road_tertiary_share",
    "road_residential_share",
    "road_service_share",
    "road_track_share",
    "active_road_share",
    "filtered_road_length_share_filled",
    "log_road_class_count",
]

BUILD_RIDGE = 1.0
POI_BASE_RIDGE = 1.0
POI_HEAD_RIDGE = 100.0
ROAD_RIDGE = 10.0


def emit(s: str = "") -> None:
    print(s, flush=True)
    with REPORT.open("a", encoding="utf-8") as f:
        f.write(s + "\n")


def fail(s: str) -> None:
    raise RuntimeError(s)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def equal_region_weights(region_series: pd.Series) -> np.ndarray:
    counts = region_series.value_counts()
    w = region_series.map(lambda r: 1.0 / counts[r]).to_numpy(dtype=float)
    return w / w.mean()


def spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.rank(method="average").corr(b.rank(method="average")))


def top_set(s: pd.Series, frac: float) -> set[int]:
    n = max(1, int(round(len(s) * frac)))
    return set(s.nlargest(n).index)


def top_overlap(a: pd.Series, b: pd.Series, frac: float) -> float:
    A = top_set(a, frac)
    B = top_set(b, frac)
    return len(A & B) / max(1, len(A))


def bounded_shortfall(observed: np.ndarray, expected_log: np.ndarray) -> np.ndarray:
    observed = np.asarray(observed, dtype=float)
    expected = np.maximum(0.0, np.expm1(expected_log))

    out = np.zeros(len(observed), dtype=float)
    valid = np.isfinite(observed) & np.isfinite(expected) & (expected > 1e-12)

    ratio = np.ones(len(observed), dtype=float)
    ratio[valid] = observed[valid] / expected[valid]
    out[valid] = 1.0 - np.clip(ratio[valid], 0.0, 1.0)
    return np.clip(out, 0.0, 1.0)


def quadratic_base_matrix(df: pd.DataFrame, predictors: list[str]) -> np.ndarray:
    X = df[predictors].to_numpy(dtype=float)
    cols = [X, X ** 2]

    interactions = []
    for i, j in itertools.combinations(range(X.shape[1]), 2):
        interactions.append((X[:, i] * X[:, j])[:, None])

    if interactions:
        cols.append(np.hstack(interactions))

    return np.hstack(cols)


def fit_ridge_matrix(
    train: pd.DataFrame,
    X: np.ndarray,
    y: np.ndarray,
    ridge: float,
):
    w = equal_region_weights(train["region"])
    sw = w.sum()

    mu = (X * w[:, None]).sum(axis=0) / sw
    var = (((X - mu) ** 2) * w[:, None]).sum(axis=0) / sw
    sd = np.sqrt(var)
    sd[~np.isfinite(sd) | (sd < 1e-12)] = 1.0

    Z = (X - mu) / sd
    D = np.column_stack([np.ones(len(Z)), Z])

    rw = np.sqrt(w)
    Dw = D * rw[:, None]
    yw = y * rw

    gram = Dw.T @ Dw
    penalty = np.eye(gram.shape[0]) * ridge
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(gram + penalty, Dw.T @ yw)

    return mu, sd, beta


def predict_ridge_matrix(
    X: np.ndarray,
    mu: np.ndarray,
    sd: np.ndarray,
    beta: np.ndarray,
) -> np.ndarray:
    Z = (X - mu) / sd
    D = np.column_stack([np.ones(len(Z)), Z])
    return D @ beta


def build_design(df: pd.DataFrame) -> np.ndarray:
    return quadratic_base_matrix(df, BASE_BUILD)


def poi_base_design(df: pd.DataFrame) -> np.ndarray:
    return quadratic_base_matrix(df, BASE_POI)


def poi_head_design(df: pd.DataFrame) -> np.ndarray:
    base = quadratic_base_matrix(df, BASE_POI)
    extra = df[ROAD_MIX].to_numpy(dtype=float)
    return np.hstack([base, extra])


def road_design(df: pd.DataFrame) -> np.ndarray:
    return quadratic_base_matrix(df, ROAD_PRED)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for c in [x for x in df.columns if x not in ("region", "GEOID")]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    area = df["tract_area_km2"].clip(lower=1e-12)
    road_total = df["road_all_length_km"].fillna(0).clip(lower=0)
    road_denom = road_total.where(road_total > 1e-12, np.nan)

    df["infra_density_per_km2"] = df["infrastructure_count"].fillna(0) / area

    df["log_area"] = np.log1p(area)
    df["log_building_density"] = np.log1p(
        df["building_density_per_km2"].fillna(0).clip(lower=0)
    )
    df["log_poi_density"] = np.log1p(
        df["poi_density_per_km2"].fillna(0).clip(lower=0)
    )
    df["log_road_all_density"] = np.log1p(
        df["road_all_density_km_per_km2"].fillna(0).clip(lower=0)
    )
    df["log_infra_density"] = np.log1p(
        df["infra_density_per_km2"].clip(lower=0)
    )
    df["log_rail_density"] = np.log1p(
        df["rail_density_km_per_km2"].fillna(0).clip(lower=0)
    )

    df["log_road_class_count"] = np.log1p(
        df["road_all_class_count"].fillna(0).clip(lower=0)
    )
    df["filtered_road_length_share_filled"] = (
        df["filtered_road_length_share"].fillna(0.0)
    )

    share_defs = {
        "road_motorway_share": "road_motorway_km",
        "road_trunk_share": "road_trunk_km",
        "road_primary_share": "road_primary_km",
        "road_secondary_share": "road_secondary_km",
        "road_tertiary_share": "road_tertiary_km",
        "road_residential_share": "road_residential_km",
        "road_service_share": "road_service_km",
        "road_track_share": "road_track_km",
    }

    for out, src in share_defs.items():
        df[out] = (
            df[src].fillna(0) / road_denom
        ).fillna(0.0).clip(0, 1)

    active = (
        df["road_footway_km"].fillna(0)
        + df["road_path_km"].fillna(0)
        + df["road_cycleway_km"].fillna(0)
    )
    df["active_road_share"] = (
        active / road_denom
    ).fillna(0.0).clip(0, 1)

    road_cols = [
        "road_all_length_km",
        "road_all_segment_count",
        "road_all_class_count",
        "road_motorway_km",
        "road_trunk_km",
        "road_primary_km",
        "road_secondary_km",
        "road_service_km",
        "road_track_km",
        "road_footway_km",
        "road_path_km",
        "road_cycleway_km",
        "road_living_street_km",
    ]
    for c in road_cols:
        df[c] = df[c].fillna(0)

    df["major_road_km"] = (
        df["road_motorway_km"]
        + df["road_trunk_km"]
        + df["road_primary_km"]
        + df["road_secondary_km"]
    )
    df["major_road_density"] = df["major_road_km"] / area

    df["minor_context_km"] = (
        df["road_all_length_km"] - df["major_road_km"]
    ).clip(lower=0)
    df["minor_context_density"] = df["minor_context_km"] / area
    df["road_all_segment_density"] = df["road_all_segment_count"] / area
    df["service_density"] = df["road_service_km"] / area
    df["track_density"] = df["road_track_km"] / area
    df["active_density"] = (
        df["road_footway_km"]
        + df["road_path_km"]
        + df["road_cycleway_km"]
    ) / area
    df["living_street_density"] = df["road_living_street_km"] / area

    df["log_major_density"] = np.log1p(
        df["major_road_density"].clip(lower=0)
    )
    df["log_minor_context_density"] = np.log1p(
        df["minor_context_density"].clip(lower=0)
    )
    df["log_segment_density"] = np.log1p(
        df["road_all_segment_density"].clip(lower=0)
    )
    df["log_service_density"] = np.log1p(
        df["service_density"].clip(lower=0)
    )
    df["log_track_density"] = np.log1p(
        df["track_density"].clip(lower=0)
    )
    df["log_active_density"] = np.log1p(
        df["active_density"].clip(lower=0)
    )
    df["log_living_street_density"] = np.log1p(
        df["living_street_density"].clip(lower=0)
    )
    df["log_class_count"] = np.log1p(
        df["road_all_class_count"].clip(lower=0)
    )

    needed = sorted(
        set(
            BASE_BUILD
            + BASE_POI
            + ROAD_PRED
            + ROAD_MIX
            + [
                "log_building_density",
                "log_poi_density",
                "log_major_density",
            ]
        )
    )

    if not np.isfinite(df[needed].to_numpy(dtype=float)).all():
        fail("non-finite V2-21 prepared inputs")

    return df


def score_fold(train: pd.DataFrame, test: pd.DataFrame):
    # Building: frozen V2-13 quadratic-ridge1
    bX = build_design(train)
    bY = train["log_building_density"].to_numpy(dtype=float)
    b_mu, b_sd, b_beta = fit_ridge_matrix(
        train, bX, bY, BUILD_RIDGE
    )
    b_pred = predict_ridge_matrix(
        build_design(test), b_mu, b_sd, b_beta
    )

    # POI base: frozen V2-13 quadratic-ridge1
    p0X = poi_base_design(train)
    pY = train["log_poi_density"].to_numpy(dtype=float)
    p0_mu, p0_sd, p0_beta = fit_ridge_matrix(
        train, p0X, pY, POI_BASE_RIDGE
    )
    p0_pred = predict_ridge_matrix(
        poi_base_design(test), p0_mu, p0_sd, p0_beta
    )

    # POI controlled head: base quadratic + linear road-mix, ridge100
    p1X = poi_head_design(train)
    p1_mu, p1_sd, p1_beta = fit_ridge_matrix(
        train, p1X, pY, POI_HEAD_RIDGE
    )
    p1_pred = predict_ridge_matrix(
        poi_head_design(test), p1_mu, p1_sd, p1_beta
    )

    # Fixed 50/50 blend in expected log-density space
    p50_pred = (1.0 - ALPHA) * p0_pred + ALPHA * p1_pred

    # Road: frozen V2-13 road-internal quadratic-ridge10
    rX = road_design(train)
    rY = train["log_major_density"].to_numpy(dtype=float)
    r_mu, r_sd, r_beta = fit_ridge_matrix(
        train, rX, rY, ROAD_RIDGE
    )
    r_pred = predict_ridge_matrix(
        road_design(test), r_mu, r_sd, r_beta
    )

    b_short = bounded_shortfall(
        test["building_density_per_km2"].to_numpy(dtype=float),
        b_pred,
    )
    p0_short = bounded_shortfall(
        test["poi_density_per_km2"].to_numpy(dtype=float),
        p0_pred,
    )
    p1_short = bounded_shortfall(
        test["poi_density_per_km2"].to_numpy(dtype=float),
        p1_pred,
    )
    p50_short = bounded_shortfall(
        test["poi_density_per_km2"].to_numpy(dtype=float),
        p50_pred,
    )
    r_short = bounded_shortfall(
        test["major_road_density"].to_numpy(dtype=float),
        r_pred,
    )

    mean = np.mean(
        np.column_stack([b_short, p50_short, r_short]),
        axis=1,
    )

    return {
        "building": b_short,
        "poi_base": p0_short,
        "poi_head": p1_short,
        "poi_alpha50": p50_short,
        "road": r_short,
        "mean": mean,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    INSPECT.mkdir(parents=True, exist_ok=True)

    REPORT.unlink(missing_ok=True)
    MANIFEST.unlink(missing_ok=True)

    emit("===== BIAS BOUNTY V2-21 — ALPHA50 REFERENCE-FREE CANDIDATE FREEZE =====")
    emit("SOURCE_FAMILY=V2-20")
    emit("ALPHA=0.50")
    emit("BLEND_SPACE=EXPECTED LOG POI DENSITY")
    emit("BUILDING=V2-13 QUADRATIC-RIDGE1")
    emit("POI_BASE=V2-13 QUADRATIC-RIDGE1")
    emit("POI_HEAD=CONTROLLED ROADMIX LINEAR HEAD RIDGE100")
    emit("ROAD=V2-13 QUADRATIC-RIDGE10 ROAD-INTERNAL")
    emit("AGGREGATION=EQUAL ARITHMETIC MEAN")
    emit("TRAINING_WEIGHTING=REGION-BALANCED")
    emit("PREDICTION_SCHEME=LEAVE-ONE-REGION-OUT")
    emit("OLD_RECON_IMPORTED=NO")
    emit("WITHDRAWN_REFERENCE_LAYERS_READ=NO")
    emit("ACS_VALUES_READ=NO")
    emit("NATIONAL_STRATA_VALUES_READ=NO")
    emit("LEADERBOARD_FEEDBACK_USED=NO")
    emit("OLD_TARGET_VALUES_USED=NO")
    emit("LEADERBOARD_SUBMISSION_GENERATED=NO")
    emit()

    if not FEATURES_IN.exists():
        fail(f"missing features: {FEATURES_IN}")
    if not V213_IN.exists():
        fail(f"missing V2-13 baseline: {V213_IN}")
    if not V220_IN.exists():
        fail(f"missing V2-20 output: {V220_IN}")

    feature_sha = sha256_file(FEATURES_IN)
    emit(f"FEATURES_SHA256={feature_sha}")

    feat = pd.read_csv(FEATURES_IN, dtype={"GEOID": str})
    v213 = pd.read_csv(V213_IN, dtype={"GEOID": str})
    v220 = pd.read_csv(V220_IN, dtype={"GEOID": str})

    for name, df0 in (
        ("features", feat),
        ("v2_13", v213),
        ("v2_20", v220),
    ):
        if len(df0) != EXPECTED_ROWS:
            fail(f"{name}: row-count drift")
        if df0["GEOID"].nunique() != EXPECTED_ROWS:
            fail(f"{name}: GEOID uniqueness drift")

    df = prepare(feat)

    df = df.merge(
        v213[["region", "GEOID", "v2_13_mean"]],
        on=["region", "GEOID"],
        how="inner",
        validate="one_to_one",
    )

    df = df.merge(
        v220[
            [
                "region",
                "GEOID",
                "full_a050_poi",
                "full_a050_mean",
            ]
        ],
        on=["region", "GEOID"],
        how="inner",
        validate="one_to_one",
    )

    if len(df) != EXPECTED_ROWS:
        fail("merged membership drift")

    for region, n in EXPECTED_REGIONS.items():
        got = int((df["region"] == region).sum())
        if got != n:
            fail(f"{region}: expected {n}, got {got}")

    output_cols = [
        "model_building",
        "model_poi_base",
        "model_poi_head",
        "model_poi_alpha50",
        "model_road",
        "v2_21_mean",
    ]
    for c in output_cols:
        df[c] = np.nan

    for heldout in EXPECTED_REGIONS:
        train = df[df["region"] != heldout].copy()
        test = df[df["region"] == heldout].copy()
        result = score_fold(train, test)

        idx = test.index
        df.loc[idx, "model_building"] = result["building"]
        df.loc[idx, "model_poi_base"] = result["poi_base"]
        df.loc[idx, "model_poi_head"] = result["poi_head"]
        df.loc[idx, "model_poi_alpha50"] = result["poi_alpha50"]
        df.loc[idx, "model_road"] = result["road"]
        df.loc[idx, "v2_21_mean"] = result["mean"]

    if not np.isfinite(df[output_cols].to_numpy(dtype=float)).all():
        fail("non-finite V2-21 outputs")

    if (
        (df[output_cols] < -1e-12).any().any()
        or (df[output_cols] > 1.0 + 1e-12).any().any()
    ):
        fail("V2-21 output outside [0,1]")

    # Exact reproduction against V2-20 alpha50
    poi_repro = float(
        (
            df["model_poi_alpha50"]
            - df["full_a050_poi"]
        ).abs().max()
    )
    mean_repro = float(
        (
            df["v2_21_mean"]
            - df["full_a050_mean"]
        ).abs().max()
    )

    emit(f"V2_20_ALPHA50_POI_REPRO_MAX_ABS_DELTA={poi_repro:.12g}")
    emit(f"V2_20_ALPHA50_MEAN_REPRO_MAX_ABS_DELTA={mean_repro:.12g}")

    if poi_repro > 1e-10 or mean_repro > 1e-10:
        fail("V2-20 alpha50 reproduction failure")

    # Region audit
    audit_rows = []

    for scope, idx in [
        ("ALL", df.index),
        *[
            (region, df.index[df["region"] == region])
            for region in EXPECTED_REGIONS
        ],
    ]:
        s = df.loc[idx, "v2_21_mean"]
        old = df.loc[idx, "v2_13_mean"]
        d = (s - old).abs()

        audit_rows.append(
            {
                "scope": scope,
                "rows": len(idx),
                "mean": float(s.mean()),
                "median": float(s.median()),
                "p05": float(s.quantile(0.05)),
                "p95": float(s.quantile(0.95)),
                "min": float(s.min()),
                "max": float(s.max()),
                "zero_share": float((s <= 1e-12).mean()),
                "one_share": float((s >= 1.0 - 1e-12).mean()),
                "spearman_vs_v2_13": spearman(s, old),
                "top05_overlap_vs_v2_13": top_overlap(s, old, 0.05),
                "top10_overlap_vs_v2_13": top_overlap(s, old, 0.10),
                "top20_overlap_vs_v2_13": top_overlap(s, old, 0.20),
                "mean_abs_delta_vs_v2_13": float(d.mean()),
                "p95_abs_delta_vs_v2_13": float(d.quantile(0.95)),
            }
        )

    audit_df = pd.DataFrame(audit_rows)
    audit_df.to_csv(REGION_AUDIT, index=False)

    # Component influence and top-tail capture
    influence_rows = []
    primary = df["v2_21_mean"]

    for component in [
        "model_building",
        "model_poi_alpha50",
        "model_road",
    ]:
        influence_rows.append(
            {
                "component": component,
                "spearman_with_mean": spearman(df[component], primary),
                "top05_capture": top_overlap(
                    df[component], primary, 0.05
                ),
                "top10_capture": top_overlap(
                    df[component], primary, 0.10
                ),
                "top20_capture": top_overlap(
                    df[component], primary, 0.20
                ),
            }
        )

    influence_df = pd.DataFrame(influence_rows)
    influence_df.to_csv(INFLUENCE, index=False)

    # Detailed baseline comparison
    cmp_rows = []

    for region in ["ALL", *EXPECTED_REGIONS.keys()]:
        if region == "ALL":
            idx = df.index
        else:
            idx = df.index[df["region"] == region]

        old = df.loc[idx, "v2_13_mean"]
        new = df.loc[idx, "v2_21_mean"]
        d = (new - old).abs()

        cmp_rows.append(
            {
                "scope": region,
                "rows": len(idx),
                "spearman": spearman(old, new),
                "top05_overlap": top_overlap(old, new, 0.05),
                "top10_overlap": top_overlap(old, new, 0.10),
                "top20_overlap": top_overlap(old, new, 0.20),
                "mean_abs_delta": float(d.mean()),
                "p95_abs_delta": float(d.quantile(0.95)),
                "max_abs_delta": float(d.max()),
            }
        )

    cmp_df = pd.DataFrame(cmp_rows)
    cmp_df.to_csv(BASELINE_CMP, index=False)

    final_cols = [
        "region",
        "GEOID",
        "model_building",
        "model_poi_base",
        "model_poi_head",
        "model_poi_alpha50",
        "model_road",
        "v2_21_mean",
    ]
    df[final_cols].to_csv(OUTFILE, index=False)

    output_sha = sha256_file(OUTFILE)

    manifest_lines = [
        "BIAS BOUNTY V2-21 RELEASE MANIFEST",
        f"FEATURES={FEATURES_IN}",
        f"FEATURES_SHA256={feature_sha}",
        f"OUTPUT={OUTFILE}",
        f"OUTPUT_SHA256={output_sha}",
        f"ROWS={len(df)}",
        f"UNIQUE_GEOID={df['GEOID'].nunique()}",
        f"ALPHA={ALPHA}",
        "BUILDING=quadratic-ridge1 cross-layer Overture",
        "POI_BASE=quadratic-ridge1 cross-layer Overture",
        "POI_HEAD=base quadratic + linear road-mix head ridge100",
        "POI_BLEND=50/50 in expected log-density space",
        "ROAD=quadratic-ridge10 road-internal Overture",
        "AGGREGATION=equal arithmetic mean",
        "TRAINING_WEIGHTING=region-balanced",
        "PREDICTION_SCHEME=leave-one-region-out",
        "WITHDRAWN_REFERENCE_LAYERS_READ=NO",
        "OLD_TARGET_VALUES_USED=NO",
        "LEADERBOARD_FEEDBACK_USED=NO",
        "LEADERBOARD_SUBMISSION_GENERATED=NO",
    ]
    MANIFEST.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    emit()
    emit("===== V2-21 REGION AUDIT =====")
    for _, r in audit_df.iterrows():
        emit(
            f"{r['scope']} | mean={r['mean']:.6f} "
            f"p05={r['p05']:.6f} p95={r['p95']:.6f} "
            f"vs_v2_13_spearman={r['spearman_vs_v2_13']:.6f} "
            f"top05={r['top05_overlap_vs_v2_13']:.6f} "
            f"top10={r['top10_overlap_vs_v2_13']:.6f} "
            f"top20={r['top20_overlap_vs_v2_13']:.6f}"
        )

    emit()
    emit("===== V2-21 COMPONENT INFLUENCE / CAPTURE =====")
    for _, r in influence_df.iterrows():
        emit(
            f"{r['component']} | "
            f"spearman={r['spearman_with_mean']:.6f} "
            f"top05={r['top05_capture']:.6f} "
            f"top10={r['top10_capture']:.6f} "
            f"top20={r['top20_capture']:.6f}"
        )

    emit()
    emit(f"OUTPUT={OUTFILE}")
    emit(f"OUTPUT_SHA256={output_sha}")
    emit(f"REGION_AUDIT={REGION_AUDIT}")
    emit(f"INFLUENCE={INFLUENCE}")
    emit(f"BASELINE_COMPARISON={BASELINE_CMP}")
    emit(f"MANIFEST={MANIFEST}")
    emit("V2_21_ALPHA50_CANDIDATE_FREEZE=PASS")
    emit("LEADERBOARD_SUBMISSION_GENERATED=NO")
    emit("NEXT=HOLD MODEL TUNING; RESOLVE ORGANIZER LEGALITY BEFORE ANY LEADERBOARD SUBMISSION")


if __name__ == "__main__":
    main()
