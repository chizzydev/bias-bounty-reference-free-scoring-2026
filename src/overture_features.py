from __future__ import annotations

import csv
import math
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
STATE = ROOT / "inspections" / "V2-2-state"
REPORT = ROOT / "inspections" / "V2-2-report.txt"

OUT.mkdir(parents=True, exist_ok=True)
STATE.mkdir(parents=True, exist_ok=True)

BASE = "s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"

REGIONS = (
    "eastern-ok",
    "maricopa-az",
    "northern-ca",
    "south-central-tx",
    "eastern-wa",
)

EXPECTED_ROWS = {
    "eastern-ok": 1192,
    "maricopa-az": 1593,
    "northern-ca": 591,
    "south-central-tx": 6003,
    "eastern-wa": 415,
}

EXPECTED_TOTAL = 9794

FINAL = OUT / "V2-2-overture-core-features.csv"

# This factory intentionally uses only:
# - current Overture layers,
# - current tract geometry,
# - current SampleSubmission GEOIDs for membership.
#
# It does NOT read ACS, national strata values, withdrawn reference layers,
# prior target reconstructions, leaderboard outputs, or old campaign files.

def emit(s: str = "") -> None:
    print(s, flush=True)
    with REPORT.open("a", encoding="utf-8") as f:
        f.write(s + "\n")

def fail(s: str) -> None:
    raise RuntimeError(s)

def setup(region: str) -> duckdb.DuckDBPyConnection:
    tmp = STATE / f"{region}-tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("SET s3_region='us-west-2'")
    con.execute("SET s3_url_style='path'")
    con.execute("SET threads TO 2")
    con.execute("SET memory_limit='4GB'")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{str(tmp).replace(chr(39), chr(39)*2)}'")
    return con

def bbox(alias_feature: str = "f", alias_tract: str = "t") -> str:
    return (
        f"{alias_feature}.bbox.xmin <= {alias_tract}.bbox.xmax AND "
        f"{alias_feature}.bbox.xmax >= {alias_tract}.bbox.xmin AND "
        f"{alias_feature}.bbox.ymin <= {alias_tract}.bbox.ymax AND "
        f"{alias_feature}.bbox.ymax >= {alias_tract}.bbox.ymin"
    )

def write_region(region: str) -> Path:
    ref = f"{BASE}/reference/{region}"
    strata = f"{BASE}/strata/{region}"
    sample = f"{ref}/{region}-sample-submission.csv"
    tracts = f"{strata}/{region}-census-tracts.parquet"

    buildings = f"{ref}/{region}-overture-buildings.parquet"
    roads = f"{ref}/{region}-overture-roads.parquet"
    roads_all = f"{ref}/{region}-overture-roads-unfiltered.parquet"
    rail = f"{ref}/{region}-overture-rail.parquet"
    infra = f"{ref}/{region}-overture-infrastructure.parquet"
    pois = f"{ref}/{region}-overture-pois.parquet"

    emit()
    emit("=" * 88)
    emit(f"REGION={region}")
    emit("=" * 88)

    con = setup(region)

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE scored AS
        SELECT DISTINCT lpad(CAST(GEOID AS VARCHAR), 11, '0') AS GEOID
        FROM read_csv_auto('{sample}', all_varchar=true)
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE tracts AS
        SELECT
            lpad(CAST(x.GEOID AS VARCHAR), 11, '0') AS GEOID,
            x.geometry,
            x.bbox,
            ST_Transform(
                x.geometry,
                'EPSG:4326',
                'EPSG:5070',
                always_xy := true
            ) AS g5070
        FROM read_parquet('{tracts}') x
        JOIN scored s
          ON lpad(CAST(x.GEOID AS VARCHAR), 11, '0') = s.GEOID
        """
    )

    n_scored = int(con.execute("SELECT count(*) FROM scored").fetchone()[0])
    n_tracts = int(con.execute("SELECT count(*) FROM tracts").fetchone()[0])
    n_distinct = int(con.execute("SELECT count(DISTINCT GEOID) FROM tracts").fetchone()[0])

    if (n_scored, n_tracts, n_distinct) != (
        EXPECTED_ROWS[region],
        EXPECTED_ROWS[region],
        EXPECTED_ROWS[region],
    ):
        fail(
            f"{region}: membership drift scored={n_scored}, "
            f"tracts={n_tracts}, distinct={n_distinct}"
        )

    emit(f"MEMBERSHIP=PASS rows={n_tracts}")

    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE tract_base AS
        SELECT
            GEOID,
            ST_Area(g5070) / 1000000.0 AS tract_area_km2,
            ST_Perimeter(g5070) / 1000.0 AS tract_perimeter_km
        FROM tracts
        """
    )

    emit("BUILDINGS=START")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE bld_assign AS
        SELECT
            t.GEOID,
            b.sources
        FROM tracts t
        JOIN read_parquet('{buildings}') b
          ON {bbox('b', 't')}
         AND ST_Intersects(t.geometry, ST_Centroid(b.geometry))
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE bld_basic AS
        SELECT
            GEOID,
            count(*) AS building_count
        FROM bld_assign
        GROUP BY GEOID
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE bld_source_counts AS
        SELECT
            a.GEOID,
            s.dataset AS dataset,
            count(*) AS n,
            count(s.confidence) AS confidence_n,
            sum(CASE WHEN s.confidence IS NOT NULL THEN s.confidence ELSE 0 END) AS confidence_sum
        FROM bld_assign a,
             unnest(a.sources) AS u(s)
        WHERE s.dataset IS NOT NULL
        GROUP BY a.GEOID, s.dataset
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE bld_source_stats AS
        WITH x AS (
            SELECT
                *,
                sum(n) OVER (PARTITION BY GEOID) AS total_n
            FROM bld_source_counts
        )
        SELECT
            GEOID,
            count(*) AS building_source_dataset_count,
            max(n * 1.0 / total_n) AS building_source_top_share,
            -sum(
                CASE
                    WHEN n > 0 AND total_n > 0
                    THEN (n * 1.0 / total_n) * ln(n * 1.0 / total_n)
                    ELSE 0
                END
            ) AS building_source_entropy,
            sum(confidence_n) * 1.0 / sum(n) AS building_source_confidence_reported_share,
            CASE
                WHEN sum(confidence_n) > 0
                THEN sum(confidence_sum) / sum(confidence_n)
                ELSE NULL
            END AS building_source_confidence_mean
        FROM x
        GROUP BY GEOID
        """
    )
    emit("BUILDINGS=PASS")

    emit("POIS=START")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE poi_agg AS
        SELECT
            t.GEOID,
            count(*) AS poi_count,
            count(DISTINCT p.categories.primary) AS poi_primary_category_count,
            count(p.confidence) * 1.0 / count(*) AS poi_confidence_reported_share,
            avg(p.confidence) AS poi_confidence_mean
        FROM tracts t
        JOIN read_parquet('{pois}') p
          ON {bbox('p', 't')}
         AND ST_Intersects(t.geometry, p.geometry)
        GROUP BY t.GEOID
        """
    )
    emit("POIS=PASS")

    emit("INFRASTRUCTURE=START")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE infra_agg AS
        SELECT
            t.GEOID,
            count(*) AS infrastructure_count
        FROM tracts t
        JOIN read_parquet('{infra}') f
          ON {bbox('f', 't')}
         AND ST_Intersects(t.geometry, ST_Centroid(f.geometry))
        GROUP BY t.GEOID
        """
    )
    emit("INFRASTRUCTURE=PASS")

    emit("FILTERED_ROADS=START")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE road_assign AS
        SELECT
            t.GEOID,
            r.class AS road_class,
            ST_Length(
                ST_Transform(
                    r.geometry,
                    'EPSG:4326',
                    'EPSG:5070',
                    always_xy := true
                )
            ) / 1000.0 AS segment_km
        FROM tracts t
        JOIN read_parquet('{roads}') r
          ON {bbox('r', 't')}
         AND ST_Intersects(t.geometry, ST_Centroid(r.geometry))
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE road_agg AS
        SELECT
            GEOID,
            count(*) AS road_segment_count,
            sum(segment_km) AS road_length_km,

            sum(CASE WHEN road_class='motorway' THEN segment_km ELSE 0 END) AS road_motorway_km,
            sum(CASE WHEN road_class='trunk' THEN segment_km ELSE 0 END) AS road_trunk_km,
            sum(CASE WHEN road_class='primary' THEN segment_km ELSE 0 END) AS road_primary_km,
            sum(CASE WHEN road_class='secondary' THEN segment_km ELSE 0 END) AS road_secondary_km,
            sum(CASE WHEN road_class='tertiary' THEN segment_km ELSE 0 END) AS road_tertiary_km,
            sum(CASE WHEN road_class='residential' THEN segment_km ELSE 0 END) AS road_residential_km,
            sum(CASE WHEN road_class='unclassified' THEN segment_km ELSE 0 END) AS road_unclassified_km,

            count(DISTINCT road_class) AS road_class_count
        FROM road_assign
        GROUP BY GEOID
        """
    )
    emit("FILTERED_ROADS=PASS")

    emit("UNFILTERED_ROADS=START")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE road_all_assign AS
        SELECT
            t.GEOID,
            r.class AS road_class,
            ST_Length(
                ST_Transform(
                    r.geometry,
                    'EPSG:4326',
                    'EPSG:5070',
                    always_xy := true
                )
            ) / 1000.0 AS segment_km
        FROM tracts t
        JOIN read_parquet('{roads_all}') r
          ON {bbox('r', 't')}
         AND ST_Intersects(t.geometry, ST_Centroid(r.geometry))
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE road_all_agg AS
        SELECT
            GEOID,
            count(*) AS road_all_segment_count,
            sum(segment_km) AS road_all_length_km,
            sum(CASE WHEN road_class='service' THEN segment_km ELSE 0 END) AS road_service_km,
            sum(CASE WHEN road_class='track' THEN segment_km ELSE 0 END) AS road_track_km,
            sum(CASE WHEN road_class='footway' THEN segment_km ELSE 0 END) AS road_footway_km,
            sum(CASE WHEN road_class='path' THEN segment_km ELSE 0 END) AS road_path_km,
            sum(CASE WHEN road_class='cycleway' THEN segment_km ELSE 0 END) AS road_cycleway_km,
            sum(CASE WHEN road_class='living_street' THEN segment_km ELSE 0 END) AS road_living_street_km,
            count(DISTINCT road_class) AS road_all_class_count
        FROM road_all_assign
        GROUP BY GEOID
        """
    )
    emit("UNFILTERED_ROADS=PASS")

    emit("RAIL=START")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE rail_agg AS
        SELECT
            t.GEOID,
            count(*) AS rail_segment_count,
            sum(
                ST_Length(
                    ST_Transform(
                        r.geometry,
                        'EPSG:4326',
                        'EPSG:5070',
                        always_xy := true
                    )
                )
            ) / 1000.0 AS rail_length_km
        FROM tracts t
        JOIN read_parquet('{rail}') r
          ON {bbox('r', 't')}
         AND ST_Intersects(t.geometry, ST_Centroid(r.geometry))
        GROUP BY t.GEOID
        """
    )
    emit("RAIL=PASS")

    region_out = STATE / f"{region}-features.csv"

    query = """
        SELECT
            ? AS region,
            b.GEOID,
            b.tract_area_km2,
            b.tract_perimeter_km,

            coalesce(x.building_count, 0) AS building_count,
            coalesce(xs.building_source_dataset_count, 0) AS building_source_dataset_count,
            xs.building_source_top_share,
            xs.building_source_entropy,
            xs.building_source_confidence_reported_share,
            xs.building_source_confidence_mean,

            coalesce(p.poi_count, 0) AS poi_count,
            coalesce(p.poi_primary_category_count, 0) AS poi_primary_category_count,
            p.poi_confidence_reported_share,
            p.poi_confidence_mean,

            coalesce(i.infrastructure_count, 0) AS infrastructure_count,

            coalesce(r.road_segment_count, 0) AS road_segment_count,
            coalesce(r.road_length_km, 0) AS road_length_km,
            coalesce(r.road_motorway_km, 0) AS road_motorway_km,
            coalesce(r.road_trunk_km, 0) AS road_trunk_km,
            coalesce(r.road_primary_km, 0) AS road_primary_km,
            coalesce(r.road_secondary_km, 0) AS road_secondary_km,
            coalesce(r.road_tertiary_km, 0) AS road_tertiary_km,
            coalesce(r.road_residential_km, 0) AS road_residential_km,
            coalesce(r.road_unclassified_km, 0) AS road_unclassified_km,
            coalesce(r.road_class_count, 0) AS road_class_count,

            coalesce(ra.road_all_segment_count, 0) AS road_all_segment_count,
            coalesce(ra.road_all_length_km, 0) AS road_all_length_km,
            coalesce(ra.road_service_km, 0) AS road_service_km,
            coalesce(ra.road_track_km, 0) AS road_track_km,
            coalesce(ra.road_footway_km, 0) AS road_footway_km,
            coalesce(ra.road_path_km, 0) AS road_path_km,
            coalesce(ra.road_cycleway_km, 0) AS road_cycleway_km,
            coalesce(ra.road_living_street_km, 0) AS road_living_street_km,
            coalesce(ra.road_all_class_count, 0) AS road_all_class_count,

            coalesce(rr.rail_segment_count, 0) AS rail_segment_count,
            coalesce(rr.rail_length_km, 0) AS rail_length_km,

            coalesce(x.building_count, 0) / nullif(b.tract_area_km2, 0) AS building_density_per_km2,
            coalesce(p.poi_count, 0) / nullif(b.tract_area_km2, 0) AS poi_density_per_km2,
            coalesce(r.road_length_km, 0) / nullif(b.tract_area_km2, 0) AS road_density_km_per_km2,
            coalesce(ra.road_all_length_km, 0) / nullif(b.tract_area_km2, 0) AS road_all_density_km_per_km2,
            coalesce(rr.rail_length_km, 0) / nullif(b.tract_area_km2, 0) AS rail_density_km_per_km2,

            CASE
                WHEN coalesce(ra.road_all_length_km, 0) > 0
                THEN coalesce(r.road_length_km, 0) / ra.road_all_length_km
                ELSE NULL
            END AS filtered_road_length_share

        FROM tract_base b
        LEFT JOIN bld_basic x USING (GEOID)
        LEFT JOIN bld_source_stats xs USING (GEOID)
        LEFT JOIN poi_agg p USING (GEOID)
        LEFT JOIN infra_agg i USING (GEOID)
        LEFT JOIN road_agg r USING (GEOID)
        LEFT JOIN road_all_agg ra USING (GEOID)
        LEFT JOIN rail_agg rr USING (GEOID)
        ORDER BY b.GEOID
    """

    rows = con.execute(query, [region])
    cols = [d[0] for d in rows.description]
    data = rows.fetchall()
    con.close()

    if len(data) != EXPECTED_ROWS[region]:
        fail(f"{region}: output rows={len(data)}, expected={EXPECTED_ROWS[region]}")

    with region_out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        w.writerows(data)

    emit(f"REGION_FEATURES=PASS rows={len(data)} file={region_out}")
    return region_out

def main() -> None:
    REPORT.unlink(missing_ok=True)
    FINAL.unlink(missing_ok=True)

    emit("===== BIAS BOUNTY V2-2 — OVERTURE-ONLY TRACT FEATURE FACTORY =====")
    emit("OLD_RECON_IMPORTED=NO")
    emit("WITHDRAWN_REFERENCE_LAYERS_READ=NO")
    emit("ACS_VALUES_READ=NO")
    emit("NATIONAL_STRATA_VALUES_READ=NO")
    emit("LEADERBOARD_FEEDBACK_USED=NO")
    emit("MODEL_TRAINING=NO")
    emit("LEADERBOARD_SUBMISSION=NO")
    emit()

    region_files = [write_region(r) for r in REGIONS]

    all_rows: list[dict[str, str]] = []
    header: list[str] | None = None

    for p in region_files:
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if header is None:
                header = list(reader.fieldnames or [])
            elif list(reader.fieldnames or []) != header:
                fail(f"feature-column drift in {p}")
            all_rows.extend(reader)

    if header is None:
        fail("no feature rows produced")

    geoids = [r["GEOID"] for r in all_rows]
    if len(all_rows) != EXPECTED_TOTAL:
        fail(f"combined rows={len(all_rows)}, expected={EXPECTED_TOTAL}")
    if len(set(geoids)) != EXPECTED_TOTAL:
        fail("combined GEOID uniqueness failed")

    numeric_cols = [c for c in header if c not in ("region", "GEOID")]
    bad_nonfinite: list[tuple[str, str, str]] = []

    for row in all_rows:
        for col in numeric_cols:
            s = (row.get(col) or "").strip()
            if not s:
                continue
            try:
                x = float(s)
            except ValueError:
                bad_nonfinite.append((row["GEOID"], col, s))
                continue
            if not math.isfinite(x):
                bad_nonfinite.append((row["GEOID"], col, s))

    if bad_nonfinite:
        fail(f"non-finite/non-numeric values found, sample={bad_nonfinite[:10]}")

    with FINAL.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(all_rows)

    emit()
    emit(f"COMBINED_ROWS={len(all_rows)}")
    emit(f"DISTINCT_GEOIDS={len(set(geoids))}")
    emit(f"FEATURE_COLUMNS={len(header) - 2}")
    emit(f"FINAL={FINAL}")
    emit("V2_2_OVERTURE_FEATURE_FACTORY=PASS")
    emit("NEXT=REFERENCE_FREE_FEATURE_DIAGNOSTICS_AND_MODEL_CONTRACT")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Overture-only per-tract raw feature extractor")
    parser.add_argument("--region", choices=REGIONS, default=None,
        help="Optional single-region run (full five-region run by default)")
    args = parser.parse_args()
    if args.region is not None:
        REGIONS = (args.region,)
        EXPECTED_TOTAL = EXPECTED_ROWS[args.region]
    main()

