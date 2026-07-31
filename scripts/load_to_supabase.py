"""Carga los CSV del piloto ZASEVA a Supabase (schema zaseva).

Uso:
  export SUPABASE_DB_URL='postgresql://postgres:PASSWORD@db.XXX.supabase.co:5432/postgres'
  python scripts/load_to_supabase.py

O pasa la URL como primer argumento.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SQL_SETUP = ROOT / "sql" / "supabase_setup.sql"


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit(
            "Falta SUPABASE_DB_URL. Ej:\n"
            "  export SUPABASE_DB_URL='postgresql://postgres:...@db.xxx.supabase.co:5432/postgres'\n"
            "  python scripts/load_to_supabase.py"
        )

    engine = create_engine(url)
    print("1) Aplicando SQL setup (PostGIS + tablas + vistas)...")
    sql_raw = SQL_SETUP.read_text(encoding="utf-8")
    # quitar comentarios de línea y ejecutar por statement
    lines = []
    for line in sql_raw.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    with engine.begin() as conn:
        for stmt in cleaned.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))

    print("2) Cargando acuíferos...")
    oferta = pd.read_csv(DATA / "oferta_acuiferos_poniente.csv", dtype=str)
    oferta["cve_acui"] = oferta["CLV_ACUI"].str.zfill(4)
    geo = gpd.read_file(DATA / "acuiferos_poniente.geojson")
    geo["CLV_ACUI"] = geo["CLV_ACUI"].astype(str).str.zfill(4)
    acu = oferta.merge(geo[["CLV_ACUI", "geometry"]], left_on="cve_acui", right_on="CLV_ACUI", how="left")
    acu_gdf = gpd.GeoDataFrame(
        {
            "cve_acui": acu["cve_acui"],
            "nom_acui": acu["NOM_ACUI"],
            "nom_edo": acu["NOM_EDO"],
            "recarga_to_hm3": acu["RECARGA_TO"].astype(float),
            "descarga_n_hm3": acu["DESCARGA_N"].astype(float),
            "dma_negati_hm3": acu["DMA_NEGATI"].astype(float),
            "deficit_hm3": acu["DMA_NEGATI"].astype(float).abs(),
        },
        geometry=acu["geometry"],
        crs="EPSG:4326",
    )
    # multipolygon
    acu_gdf["geometry"] = acu_gdf.geometry
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE zaseva.dim_acuifero CASCADE"))
    acu_gdf = acu_gdf.set_geometry("geometry")
    acu_gdf.to_postgis("dim_acuifero", engine, schema="zaseva", if_exists="append", index=False)

    print("3) Cargando piezometría...")
    piezo = pd.read_csv(DATA / "estres_piezometrico_poniente.csv")
    piezo["cve_acui"] = piezo["cve_acui"].astype(str).str.zfill(4)
    piezo["peso_heatmap"] = piezo["tasa_abatimiento_m_anio"].clip(lower=0).fillna(0)
    piezo_gdf = gpd.GeoDataFrame(
        piezo[
            [
                "num_pozo",
                "nom_pozo",
                "cve_acui",
                "nom_acuif",
                "latitud",
                "longitud",
                "tasa_abatimiento_m_anio",
                "delta_pne_m",
                "pne_ultimo_m",
                "n_obs",
                "nivel_estres",
                "en_bbox_piloto",
                "peso_heatmap",
            ]
        ].copy(),
        geometry=gpd.points_from_xy(piezo["longitud"], piezo["latitud"]),
        crs="EPSG:4326",
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE zaseva.fact_pozo_piezometrico CASCADE"))
    piezo_gdf.to_postgis(
        "fact_pozo_piezometrico", engine, schema="zaseva", if_exists="append", index=False
    )

    print("4) Cargando REPDA...")
    repda = pd.read_csv(DATA / "oferta_repda_poniente.csv", dtype={"titulo": str, "cve_acui": str})
    if "volumen_punto_m3_anio" not in repda.columns:
        repda["volumen_punto_m3_anio"] = repda["volumen_m3_anio"]
    if "volumen_punto_hm3_anio" not in repda.columns:
        repda["volumen_punto_hm3_anio"] = repda["volumen_m3_anio"] / 1_000_000.0
    repda_gdf = gpd.GeoDataFrame(
        repda[
            [
                "titulo",
                "titular",
                "uso",
                "volumen_m3_anio",
                "volumen_hm3_anio",
                "volumen_punto_m3_anio",
                "volumen_punto_hm3_anio",
                "fecha_titulo",
                "latitud",
                "longitud",
                "cve_acui",
                "nom_acui",
                "en_bbox_piloto",
            ]
        ].copy(),
        geometry=gpd.points_from_xy(repda["longitud"], repda["latitud"]),
        crs="EPSG:4326",
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE zaseva.fact_repda_subtitulo CASCADE"))
    repda_gdf.to_postgis(
        "fact_repda_subtitulo", engine, schema="zaseva", if_exists="append", index=False
    )

    print("5) Cargando municipios / sequía...")
    sequia = pd.read_csv(DATA / "riesgo_sequia_poniente.csv", dtype=str)
    sequia_out = sequia.rename(
        columns={
            "sps": "sps",
            "msm": "msm",
            "ahorro_uso_eficiente": "ahorro_uso_eficiente",
        }
    )[
        [
            "cve_geo",
            "nombre_mun",
            "entidad",
            "sps",
            "msm",
            "ahorro_uso_eficiente",
            "con_cuenca",
            "org_cuenca",
            "fecha_corte",
        ]
    ]
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE zaseva.dim_municipio_piloto CASCADE"))
    sequia_out.to_sql(
        "dim_municipio_piloto",
        engine,
        schema="zaseva",
        if_exists="append",
        index=False,
        method="multi",
    )

    print("Listo. Revisa en Supabase → Table Editor (schema zaseva).")


if __name__ == "__main__":
    main()
