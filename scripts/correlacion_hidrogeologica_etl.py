"""
ZASEVA — ETL de correlación hidrogeológica (Sentinel-1 SAR × acuíferos × pozos)

Extrae un parche Sentinel-1 (VV/VH) sobre el AOI Corredor Poniente vía Google
Earth Engine, aplica Speckle Filter, detecta retrodispersión dieléctrica anómala
(humedad bajo asfalto), hace spatial join con acuíferos/pozos y persiste en
PostGIS (schema zaseva).

AOI Poniente (default):
  SW [-99.3100, 19.3000] · NE [-99.1500, 19.4500]

Uso:
  # 1) Aplicar schema (una vez)
  psql "$SUPABASE_DB_URL" -f sql/schema_geoespacial.sql

  # 2) Autenticar Earth Engine (una vez por máquina)
  earthengine authenticate
  # o: export EE_PROJECT=tu-gcp-project

  # 3) Correr ETL
  export SUPABASE_DB_URL='postgresql://postgres:...@db.xxx.supabase.co:5432/postgres'
  python scripts/correlacion_hidrogeologica_etl.py

  # Sin GEE / prueba local de joins + score:
  python scripts/correlacion_hidrogeologica_etl.py --dry-run

Deps: earthengine-api, geopandas, shapely, sqlalchemy, psycopg2-binary, scipy
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import ndimage
from shapely.geometry import Point, box
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SQL_SCHEMA = ROOT / "sql" / "schema_geoespacial.sql"

# Corredor Poniente — bbox canónico (glosario + brief)
AOI_SW = (-99.3100, 19.3000)
AOI_NE = (-99.1500, 19.4500)
AOI_BOUNDS = (*AOI_SW, *AOI_NE)  # minx, miny, maxx, maxy

# Pesos del Score de Severidad de Fuga (suman 1.0)
WEIGHT_SAR = 0.40
WEIGHT_ABATIMIENTO = 0.25
WEIGHT_SUBSIDENCIA = 0.20
WEIGHT_DEFICIT = 0.10
WEIGHT_SOCIAL = 0.05

# Umbral dB sobre mediana local (post-speckle) para marcar humedad anómala
DELTA_DB_THRESHOLD = 1.5
POZO_CRITICO_RADIUS_M = 800.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("zaseva.etl.sar")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def aoi_gdf() -> gpd.GeoDataFrame:
    geom = box(*AOI_BOUNDS)
    return gpd.GeoDataFrame(
        [{"aoi_id": "poniente_v1", "nombre": "Corredor Poniente"}],
        geometry=[geom],
        crs="EPSG:4326",
    )


def get_db_url(cli_url: str | None) -> str:
    url = cli_url or os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "Falta SUPABASE_DB_URL.\n"
            "  export SUPABASE_DB_URL='postgresql://postgres:...@db.xxx.supabase.co:5432/postgres'\n"
            "  python scripts/correlacion_hidrogeologica_etl.py"
        )
    return url


def _split_sql_statements(sql: str) -> list[str]:
    """Parte SQL por ';' respetando strings con comillas simples."""
    stmts: list[str] = []
    buf: list[str] = []
    in_single = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_single:
            buf.append(ch)
            if ch == "'" and i + 1 < len(sql) and sql[i + 1] == "'":
                buf.append(sql[i + 1])
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def apply_schema(engine) -> None:
    if not SQL_SCHEMA.exists():
        log.warning("No se encontró %s — se asume schema ya aplicado.", SQL_SCHEMA)
        return
    log.info("Aplicando %s ...", SQL_SCHEMA.name)
    raw = SQL_SCHEMA.read_text(encoding="utf-8")
    cleaned_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        if "--" in line:
            # No cortar '--' si está dentro de comillas simples
            out = []
            in_single = False
            j = 0
            while j < len(line):
                c = line[j]
                if c == "'" and not in_single:
                    in_single = True
                    out.append(c)
                elif c == "'" and in_single:
                    if j + 1 < len(line) and line[j + 1] == "'":
                        out.append("''")
                        j += 2
                        continue
                    in_single = False
                    out.append(c)
                elif c == "-" and not in_single and j + 1 < len(line) and line[j + 1] == "-":
                    break
                else:
                    out.append(c)
                j += 1
            line = "".join(out)
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    with engine.begin() as conn:
        for stmt in _split_sql_statements(cleaned):
            conn.execute(text(stmt))


# ---------------------------------------------------------------------------
# Speckle + detección de anomalías
# ---------------------------------------------------------------------------

def lee_sigma_filter(arr: np.ndarray, size: int = 5, num_looks: float = 4.0) -> np.ndarray:
    """Lee Sigma approx. sobre imagen en potencia lineal (no dB)."""
    arr = np.asarray(arr, dtype=np.float64)
    arr = np.where(np.isfinite(arr) & (arr > 0), arr, np.nan)
    mean = ndimage.uniform_filter(np.nan_to_num(arr, nan=0.0), size=size)
    mean_sq = ndimage.uniform_filter(np.nan_to_num(arr, nan=0.0) ** 2, size=size)
    var = np.maximum(mean_sq - mean**2, 0.0)
    # Coeficiente de variación teórico para multi-look
    cu = 1.0 / np.sqrt(num_looks)
    # Varianza del ruido
    noise_var = (mean**2) * (cu**2)
    weight = 1.0 - np.divide(noise_var, var, out=np.zeros_like(var), where=var > 0)
    weight = np.clip(weight, 0.0, 1.0)
    filtered = mean + weight * (arr - mean)
    return np.where(np.isfinite(arr), filtered, np.nan)


def linear_to_db(linear: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(linear, 1e-10))


def detect_moisture_anomalies(
    backscatter_db: np.ndarray,
    transform_origin: tuple[float, float, float, float],
    delta_threshold: float = DELTA_DB_THRESHOLD,
) -> gpd.GeoDataFrame:
    """
    Identifica píxeles con retrodispersión anómala (alta vs mediana local).

    transform_origin: (minx, maxy, xres, yres) en EPSG:4326 (yres positivo).
    """
    minx, maxy, xres, yres = transform_origin
    rows, cols = backscatter_db.shape
    local_med = ndimage.median_filter(
        np.nan_to_num(backscatter_db, nan=np.nanmedian(backscatter_db)),
        size=7,
    )
    delta = backscatter_db - local_med
    mask = np.isfinite(delta) & (delta >= delta_threshold)

    ys, xs = np.where(mask)
    if len(xs) == 0:
        return gpd.GeoDataFrame(columns=["backscatter_db", "delta_db", "geometry"], crs="EPSG:4326")

    # Submuestrear si hay demasiados píxeles (mantener densidades manejables)
    max_pts = 5000
    if len(xs) > max_pts:
        idx = np.linspace(0, len(xs) - 1, max_pts).astype(int)
        xs, ys = xs[idx], ys[idx]

    lons = minx + (xs + 0.5) * xres
    lats = maxy - (ys + 0.5) * yres
    vals = backscatter_db[ys, xs]
    deltas = delta[ys, xs]

    gdf = gpd.GeoDataFrame(
        {
            "backscatter_db": vals,
            "backscatter_db_baseline": local_med[ys, xs],
            "delta_db": deltas,
            "humedad_anomala": True,
            "latitud": lats,
            "longitud": lons,
        },
        geometry=[Point(xy) for xy in zip(lons, lats)],
        crs="EPSG:4326",
    )
    return gdf


# ---------------------------------------------------------------------------
# Google Earth Engine — Sentinel-1
# ---------------------------------------------------------------------------

def init_ee(project: str | None = None) -> Any:
    import ee

    try:
        if project:
            ee.Initialize(project=project)
        else:
            ee.Initialize()
    except Exception:
        # Fallback: autenticación interactiva / service account vía EE_SERVICE_ACCOUNT_*
        sa = os.environ.get("EE_SERVICE_ACCOUNT")
        key = os.environ.get("EE_PRIVATE_KEY_FILE")
        if sa and key and Path(key).exists():
            creds = ee.ServiceAccountCredentials(sa, key)
            ee.Initialize(creds, project=project)
        else:
            raise SystemExit(
                "Earth Engine no inicializado.\n"
                "  earthengine authenticate\n"
                "  # o export EE_PROJECT=... / EE_SERVICE_ACCOUNT + EE_PRIVATE_KEY_FILE"
            )
    return ee


def fetch_sentinel1_patch(
    days_back: int = 20,
    scale_m: int = 40,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """
    Descarga mediana VV/VH (potencia lineal) del AOI en los últimos `days_back` días.
    Retorna (vv_linear, vh_linear, meta).
    """
    ee = init_ee(os.environ.get("EE_PROJECT"))

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)
    region = ee.Geometry.Rectangle([AOI_SW[0], AOI_SW[1], AOI_NE[0], AOI_NE[1]])

    collection = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(region)
        .filterDate(str(start), str(end))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select(["VV", "VH"])
    )

    n = collection.size().getInfo()
    log.info("Escenas Sentinel-1 en ventana %s→%s: %s", start, end, n)
    if n == 0:
        raise RuntimeError("Sin escenas Sentinel-1 en la ventana/AOI. Amplía --days.")

    # S1_GRD ya viene en dB; convertir a lineal para Lee, luego volver a dB
    def db_to_linear(img: Any) -> Any:
        return ee.Image(10).pow(img.divide(10)).copyProperties(img, ["system:time_start"])

    median_db = collection.median().clip(region)
    median_lin = db_to_linear(median_db)

    # Sample as numpy via getDownloadURL / computePixels — usamos sampleRectangle-like
    # vía reduceResolution + array; aquí: ee.data.computePixels si disponible,
    # fallback getInfo sobre rejilla.
    info = median_lin.getInfo()
    _ = info  # schema check

    # Rejilla regular en el cliente (robusto en Supabase/CI)
    xres = (AOI_NE[0] - AOI_SW[0]) / max(int((AOI_NE[0] - AOI_SW[0]) * 111_320 / scale_m), 32)
    yres = (AOI_NE[1] - AOI_SW[1]) / max(int((AOI_NE[1] - AOI_SW[1]) * 110_540 / scale_m), 32)
    xs = np.arange(AOI_SW[0] + xres / 2, AOI_NE[0], xres)
    ys = np.arange(AOI_NE[1] - yres / 2, AOI_SW[1], -yres)

    points = [ee.Geometry.Point([float(x), float(y)]) for x in xs for y in ys]
    # Muestreo por lotes para no saturar
    batch = 500
    vv_vals: list[float] = []
    vh_vals: list[float] = []
    coords: list[tuple[float, float]] = [(float(x), float(y)) for y in ys for x in xs]

    for i in range(0, len(points), batch):
        fc = ee.FeatureCollection(
            [ee.Feature(points[j], {"i": j}) for j in range(i, min(i + batch, len(points)))]
        )
        sampled = median_lin.sampleRegions(collection=fc, scale=scale_m, geometries=False)
        rows = sampled.getInfo()["features"]
        by_i = {int(f["properties"]["i"]): f["properties"] for f in rows}
        for j in range(i, min(i + batch, len(points))):
            props = by_i.get(j, {})
            vv_vals.append(float(props.get("VV", np.nan)))
            vh_vals.append(float(props.get("VH", np.nan)))

    ncols, nrows = len(xs), len(ys)
    vv = np.array(vv_vals, dtype=np.float64).reshape(nrows, ncols)
    vh = np.array(vh_vals, dtype=np.float64).reshape(nrows, ncols)

    meta = {
        "fecha_inicio_ventana": start.isoformat(),
        "fecha_fin_ventana": end.isoformat(),
        "fecha_escena": end.isoformat(),
        "n_escenas": n,
        "scale_m": scale_m,
        "transform": (AOI_SW[0], AOI_NE[1], xres, yres),
        "coords_shape": (nrows, ncols),
    }
    return vv, vh, meta


def dry_run_synthetic_anomalies(rng: np.random.Generator | None = None) -> gpd.GeoDataFrame:
    """Genera puntos sintéticos en el AOI para probar joins sin Earth Engine."""
    rng = rng or np.random.default_rng(42)
    n = 120
    lons = rng.uniform(AOI_SW[0], AOI_NE[0], n)
    lats = rng.uniform(AOI_SW[1], AOI_NE[1], n)
    baseline = rng.uniform(-14.0, -10.0, n)
    delta = rng.uniform(DELTA_DB_THRESHOLD, 4.0, n)
    gdf = gpd.GeoDataFrame(
        {
            "backscatter_db": baseline + delta,
            "backscatter_db_baseline": baseline,
            "delta_db": delta,
            "humedad_anomala": True,
            "latitud": lats,
            "longitud": lons,
            "polarizacion": "VV_VH",
        },
        geometry=[Point(xy) for xy in zip(lons, lats)],
        crs="EPSG:4326",
    )
    return gdf


# ---------------------------------------------------------------------------
# Carga de capas locales / PostGIS + spatial joins
# ---------------------------------------------------------------------------

def load_acuiferos(engine) -> gpd.GeoDataFrame:
    try:
        gdf = gpd.read_postgis(
            "SELECT cve_acui, nom_acui, nom_edo, recarga_hm3, dma_hm3, deficit_hm3, geom "
            "FROM zaseva.acuiferos_conagua",
            engine,
            geom_col="geom",
        )
        if not gdf.empty:
            return gdf
    except Exception as exc:
        log.warning("PostGIS acuíferos no disponible (%s). Usando GeoJSON local.", exc)

    geo = gpd.read_file(DATA / "acuiferos_poniente.geojson")
    oferta = pd.read_csv(DATA / "oferta_acuiferos_poniente.csv", dtype=str)
    oferta["cve_acui"] = oferta["CLV_ACUI"].str.zfill(4)
    geo["CLV_ACUI"] = geo["CLV_ACUI"].astype(str).str.zfill(4)
    m = oferta.merge(geo[["CLV_ACUI", "geometry"]], left_on="cve_acui", right_on="CLV_ACUI")
    return gpd.GeoDataFrame(
        {
            "cve_acui": m["cve_acui"],
            "nom_acui": m["NOM_ACUI"],
            "nom_edo": m["NOM_EDO"],
            "recarga_hm3": m["RECARGA_TO"].astype(float),
            "dma_hm3": m["DMA_NEGATI"].astype(float),
            "deficit_hm3": m["DMA_NEGATI"].astype(float).abs(),
        },
        geometry=m["geometry"],
        crs="EPSG:4326",
    )


def load_pozos(engine) -> gpd.GeoDataFrame:
    try:
        gdf = gpd.read_postgis(
            "SELECT pozo_id, num_pozo, nom_pozo, cve_acui, nom_acui, latitud, longitud, "
            "pne_ultimo_m, tasa_abatimiento_m_anio, nivel_estres, "
            "volumen_concesionado_m3_anio, geom "
            "FROM zaseva.pozos_piezometricos",
            engine,
            geom_col="geom",
        )
        if not gdf.empty:
            return gdf
    except Exception as exc:
        log.warning("PostGIS pozos no disponible (%s). Usando CSV local.", exc)

    piezo = pd.read_csv(DATA / "estres_piezometrico_poniente.csv")
    piezo["cve_acui"] = piezo["cve_acui"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    return gpd.GeoDataFrame(
        {
            "pozo_id": piezo["num_pozo"].astype(int),
            "num_pozo": piezo["num_pozo"].astype(int),
            "nom_pozo": piezo["nom_pozo"].astype(str),
            "cve_acui": piezo["cve_acui"],
            "nom_acui": piezo.get("nom_acuif"),
            "latitud": piezo["latitud"],
            "longitud": piezo["longitud"],
            "pne_ultimo_m": piezo["pne_ultimo_m"],
            "tasa_abatimiento_m_anio": piezo["tasa_abatimiento_m_anio"],
            "nivel_estres": piezo["nivel_estres"],
            "volumen_concesionado_m3_anio": np.nan,
        },
        geometry=gpd.points_from_xy(piezo["longitud"], piezo["latitud"]),
        crs="EPSG:4326",
    )


def load_colonias() -> gpd.GeoDataFrame:
    path = DATA / "colonias_cdmx_simplificado.geojson"
    if path.exists():
        gdf = gpd.read_file(path)
        # Normalizar columnas esperadas
        rename = {}
        for c in gdf.columns:
            cl = c.lower()
            if cl in {"colonia", "nombre", "nomgeo"} and "colonia" not in gdf.columns:
                rename[c] = "colonia"
            if cl in {"alcaldia", "municipio", "nom_mun"} and "alcaldia" not in gdf.columns:
                rename[c] = "alcaldia"
            if cl in {"id", "id_colonia", "cve_col"} and "id_colonia" not in gdf.columns:
                rename[c] = "id_colonia"
        gdf = gdf.rename(columns=rename)
        if "id_colonia" not in gdf.columns:
            gdf["id_colonia"] = gdf.index.astype(str)
        return gdf.to_crs("EPSG:4326")

    csv = pd.read_csv(DATA / "colonias_cdmx.csv")
    return gpd.GeoDataFrame(
        {
            "id_colonia": csv["id_colonia"].astype(str),
            "colonia": csv["colonia"],
            "alcaldia": csv["alcaldia"],
            "en_poniente": csv.get("en_poniente", False),
            "poblacion": csv.get("poblacion"),
            "latitud_centro": csv["latitud_centro"],
            "longitud_centro": csv["longitud_centro"],
        },
        geometry=gpd.points_from_xy(csv["longitud_centro"], csv["latitud_centro"]),
        crs="EPSG:4326",
    )


def load_subsidencia(engine) -> gpd.GeoDataFrame:
    try:
        gdf = gpd.read_postgis(
            "SELECT zona_id, nombre, tasa_hundimiento_mm_anio, severidad, geom "
            "FROM zaseva.zonas_subsidencia",
            engine,
            geom_col="geom",
        )
        return gdf
    except Exception:
        return gpd.GeoDataFrame(
            columns=["zona_id", "nombre", "tasa_hundimiento_mm_anio", "severidad", "geometry"],
            geometry="geometry",
            crs="EPSG:4326",
        )


def _as_geometry_named(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Normaliza la columna activa de geometría a nombre 'geometry'."""
    if gdf is None or gdf.empty:
        if gdf is not None and gdf.geometry.name != "geometry":
            return gdf.rename_geometry("geometry")
        return gdf
    out = gdf.copy()
    if out.geometry.name != "geometry":
        out = out.rename_geometry("geometry")
    return out


def spatial_enrich(
    sar: gpd.GeoDataFrame,
    acuiferos: gpd.GeoDataFrame,
    pozos: gpd.GeoDataFrame,
    colonias: gpd.GeoDataFrame,
    subsidencia: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Spatial join SAR → acuífero, colonia, pozo crítico cercano, subsidencia."""
    out = _as_geometry_named(sar)
    acuiferos = _as_geometry_named(acuiferos)
    pozos = _as_geometry_named(pozos)
    colonias = _as_geometry_named(colonias)
    subsidencia = _as_geometry_named(subsidencia)

    if out.crs is None:
        out = out.set_crs("EPSG:4326")

    # Acuífero subyacente
    acu_cols = [c for c in ["cve_acui", "nom_acui", "deficit_hm3", "geometry"] if c in acuiferos.columns or c == "geometry"]
    joined = gpd.sjoin(
        out,
        acuiferos[acu_cols],
        how="left",
        predicate="within",
    )
    # sjoin puede duplicar; quedarnos con el primero
    joined = joined[~joined.index.duplicated(keep="first")]
    out["cve_acui"] = joined.get("cve_acui")
    out["nom_acui"] = joined.get("nom_acui")
    out["deficit_hm3"] = joined.get("deficit_hm3")

    # Colonia / alcaldía
    if not colonias.empty:
        cols = colonias.copy()
        # Si son puntos centroide, buffer ~400 m para assignación aproximada
        if cols.geom_type.isin(["Point"]).all():
            cols = cols.to_crs(32614)  # UTM 14N (CDMX/Edomex)
            cols["geometry"] = cols.buffer(400)
            cols = cols.to_crs(4326)
        keep = [c for c in ["id_colonia", "colonia", "alcaldia", "geometry"] if c in cols.columns or c == "geometry"]
        cj = gpd.sjoin(
            out[["geometry"]],
            cols[keep],
            how="left",
            predicate="intersects",
        )
        cj = cj[~cj.index.duplicated(keep="first")]
        out["id_colonia"] = cj.get("id_colonia")
        out["colonia"] = cj.get("colonia")
        out["alcaldia"] = cj.get("alcaldia")

    # Pozo crítico más cercano (solo ALTO / MEDIO)
    crit = pozos[pozos["nivel_estres"].astype(str).str.upper().isin(["ALTO", "MEDIO"])].copy()
    if crit.empty:
        crit = pozos.copy()
    out_m = out.to_crs(32614)
    crit_m = crit.to_crs(32614)
    crit_keep = [
        c
        for c in ["pozo_id", "num_pozo", "nivel_estres", "tasa_abatimiento_m_anio", "geometry"]
        if c in crit_m.columns or c == "geometry"
    ]
    nearest = gpd.sjoin_nearest(
        out_m[["geometry"]],
        crit_m[crit_keep],
        how="left",
        max_distance=POZO_CRITICO_RADIUS_M,
        distance_col="dist_pozo_critico_m",
    )
    nearest = nearest[~nearest.index.duplicated(keep="first")]
    out["pozo_critico_id"] = nearest.get("pozo_id")
    out["dist_pozo_critico_m"] = nearest.get("dist_pozo_critico_m")
    out["pozo_nivel_estres"] = nearest.get("nivel_estres")
    out["tasa_abatimiento_m_anio"] = nearest.get("tasa_abatimiento_m_anio")

    # Subsidencia
    if not subsidencia.empty:
        sub_keep = [
            c
            for c in ["tasa_hundimiento_mm_anio", "severidad", "geometry"]
            if c in subsidencia.columns or c == "geometry"
        ]
        sj = gpd.sjoin(
            out[["geometry"]],
            subsidencia[sub_keep],
            how="left",
            predicate="within",
        )
        sj = sj[~sj.index.duplicated(keep="first")]
        out["tasa_hundimiento_mm_anio"] = sj.get("tasa_hundimiento_mm_anio")
        out["subsidencia_severidad"] = sj.get("severidad")
    else:
        out["tasa_hundimiento_mm_anio"] = np.nan
        out["subsidencia_severidad"] = None

    return out


def _num(val: Any, default: float = 0.0) -> float:
    """Convierte a float finito; NaN/None → default."""
    try:
        if val is None or (isinstance(val, float) and not np.isfinite(val)):
            return default
        if pd.isna(val):
            return default
        v = float(val)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def score_row(row: pd.Series) -> dict[str, float]:
    """Calcula componentes y score 0–100 de severidad de fuga."""
    # SAR: delta_db normalizado (1.5 dB → ~40, 4 dB → ~100)
    delta = _num(row.get("delta_db"), 0.0)
    score_sar = float(np.clip((delta / 4.0) * 100.0, 0, 100))

    # Abatimiento (m/año): 0.5 → 40, ≥2 → 100
    abat = _num(row.get("tasa_abatimiento_m_anio"), 0.0)
    if str(row.get("pozo_nivel_estres") or "").upper() == "ALTO":
        abat = max(abat, 1.2)
    score_abat = float(np.clip((abat / 2.0) * 100.0, 0, 100))

    # Subsidencia mm/año
    hund_v = _num(row.get("tasa_hundimiento_mm_anio"), default=np.nan)
    sev = str(row.get("subsidencia_severidad") or "").upper()
    if np.isfinite(hund_v):
        score_sub = float(np.clip((hund_v / 150.0) * 100.0, 0, 100))
    elif sev == "ALTA":
        score_sub = 80.0
    elif sev == "MEDIA":
        score_sub = 50.0
    elif sev == "BAJA":
        score_sub = 25.0
    else:
        score_sub = 0.0

    # Déficit acuífero (hm³): 100 → 20, 480 → ~100
    deficit = _num(row.get("deficit_hm3"), 0.0)
    score_def = float(np.clip((deficit / 500.0) * 100.0, 0, 100))

    score_social = _num(row.get("score_social"), 0.0)

    total = (
        WEIGHT_SAR * score_sar
        + WEIGHT_ABATIMIENTO * score_abat
        + WEIGHT_SUBSIDENCIA * score_sub
        + WEIGHT_DEFICIT * score_def
        + WEIGHT_SOCIAL * score_social
    )
    return {
        "score_sar_humedad": score_sar,
        "score_abatimiento": score_abat,
        "score_subsidencia": score_sub,
        "score_deficit_acui": score_def,
        "score_social": score_social,
        "score_severidad_fuga": float(np.clip(total, 0, 100)),
    }


# ---------------------------------------------------------------------------
# Persistencia PostGIS
# ---------------------------------------------------------------------------

def _ensure_geom_column(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Asegura que la geometría activa se llame 'geom' (PostGIS)."""
    out = gdf.copy()
    geom_name = out.geometry.name
    if geom_name == "geom":
        return out
    # Si ya existe una columna 'geom' no-activa, elimínala antes de renombrar
    if "geom" in out.columns and geom_name != "geom":
        out = out.drop(columns=["geom"])
    return out.rename_geometry("geom")


def upsert_reference_layers(engine, acuiferos: gpd.GeoDataFrame, pozos: gpd.GeoDataFrame) -> None:
    """Sincroniza acuíferos/pozos locales hacia las tablas canónicas del schema nuevo."""
    from shapely.geometry import MultiPolygon

    def as_multi(g):
        if g is None or g.is_empty:
            return None
        if g.geom_type == "MultiPolygon":
            return g
        if g.geom_type == "Polygon":
            return MultiPolygon([g])
        return g

    acu = acuiferos.copy()
    if "recarga_hm3" not in acu.columns:
        acu["recarga_hm3"] = np.nan
    if "dma_hm3" not in acu.columns:
        acu["dma_hm3"] = -acu["deficit_hm3"]
    acu["fecha_corte"] = date.today()
    acu["fuente"] = "CONAGUA-DMA"
    acu = acu.set_geometry(acu.geometry.apply(as_multi))
    acu = _ensure_geom_column(acu)

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE zaseva.acuiferos_conagua CASCADE"))
    cols = [
        "cve_acui",
        "nom_acui",
        "nom_edo",
        "recarga_hm3",
        "dma_hm3",
        "deficit_hm3",
        "fuente",
        "fecha_corte",
        "geom",
    ]
    for c in cols:
        if c not in acu.columns and c != "geom":
            acu[c] = None
    acu[cols].to_postgis("acuiferos_conagua", engine, schema="zaseva", if_exists="append", index=False)

    pz = _ensure_geom_column(pozos.copy())
    pz["en_bbox_piloto"] = True
    pz["fuente"] = "CONAGUA-PIEZO/REPDA"
    # Drop serial pozo_id if present so DB assigns, keep num_pozo
    write_cols = [
        c
        for c in [
            "num_pozo",
            "nom_pozo",
            "cve_acui",
            "nom_acui",
            "latitud",
            "longitud",
            "pne_ultimo_m",
            "tasa_abatimiento_m_anio",
            "nivel_estres",
            "volumen_concesionado_m3_anio",
            "en_bbox_piloto",
            "fuente",
            "geom",
        ]
        if c in pz.columns or c == "geom"
    ]
    for c in write_cols:
        if c not in pz.columns and c != "geom":
            pz[c] = None
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE zaseva.pozos_piezometricos CASCADE"))
    pz[write_cols].to_postgis(
        "pozos_piezometricos", engine, schema="zaseva", if_exists="append", index=False
    )


def persist_results(
    engine,
    run_id: uuid.UUID,
    meta: dict[str, Any],
    enriched: gpd.GeoDataFrame,
) -> None:
    fecha_escena = date.fromisoformat(meta["fecha_escena"])
    fecha_ini = date.fromisoformat(meta["fecha_inicio_ventana"])
    fecha_fin = date.fromisoformat(meta["fecha_fin_ventana"])

    # --- anomalías SAR ---
    anom = enriched.copy()
    anom["run_id"] = str(run_id)
    anom["fecha_escena"] = fecha_escena
    anom["fecha_inicio_ventana"] = fecha_ini
    anom["fecha_fin_ventana"] = fecha_fin
    if "polarizacion" not in anom.columns:
        anom["polarizacion"] = "VV_VH"
    anom["polarizacion"] = anom["polarizacion"].fillna("VV_VH")
    anom["speckle_filtrado"] = True
    anom = _ensure_geom_column(anom)

    # Resolver pozo_critico_id → FK real en tabla (por num_pozo)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM zaseva.anomalias_satelitales_sar WHERE run_id = :r"),
            {"r": str(run_id)},
        )
        map_df = pd.read_sql(
            text("SELECT pozo_id, num_pozo FROM zaseva.pozos_piezometricos"),
            conn,
        )
    if not map_df.empty and "pozo_critico_id" in anom.columns:
        m = dict(zip(map_df["num_pozo"].astype(int), map_df["pozo_id"]))
        anom["pozo_critico_id"] = anom["pozo_critico_id"].apply(
            lambda x: m.get(int(x)) if pd.notna(x) else None
        )

    sar_cols = [
        "run_id",
        "fecha_escena",
        "fecha_inicio_ventana",
        "fecha_fin_ventana",
        "polarizacion",
        "backscatter_db",
        "backscatter_db_baseline",
        "delta_db",
        "humedad_anomala",
        "speckle_filtrado",
        "cve_acui",
        "pozo_critico_id",
        "dist_pozo_critico_m",
        "latitud",
        "longitud",
        "geom",
    ]
    for c in sar_cols:
        if c not in anom.columns and c != "geom":
            anom[c] = None
    anom[sar_cols].to_postgis(
        "anomalias_satelitales_sar", engine, schema="zaseva", if_exists="append", index=False
    )

    # --- mapa salud / score ---
    scores = enriched.apply(lambda r: pd.Series(score_row(r)), axis=1)
    salud = enriched.copy()
    for c in scores.columns:
        salud[c] = scores[c]
    salud["run_id"] = str(run_id)
    salud["fecha_calculo"] = date.today()
    salud["n_anomalias_sar"] = 1
    salud["n_pozos_criticos"] = salud["pozo_critico_id"].notna().astype(int)
    salud["n_reportes_social"] = 0
    salud["deficit_acui_hm3"] = salud.get("deficit_hm3")
    salud["detalle"] = [
        json.dumps(
            {
                "weights": {
                    "sar": WEIGHT_SAR,
                    "abatimiento": WEIGHT_ABATIMIENTO,
                    "subsidencia": WEIGHT_SUBSIDENCIA,
                    "deficit": WEIGHT_DEFICIT,
                    "social": WEIGHT_SOCIAL,
                }
            }
        )
    ] * len(salud)
    salud = _ensure_geom_column(salud)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM zaseva.mapa_salud_red_correlacionado WHERE run_id = :r"),
            {"r": str(run_id)},
        )

    salud_cols = [
        "run_id",
        "fecha_calculo",
        "id_colonia",
        "colonia",
        "alcaldia",
        "cve_acui",
        "score_sar_humedad",
        "score_subsidencia",
        "score_abatimiento",
        "score_deficit_acui",
        "score_social",
        "score_severidad_fuga",
        "n_anomalias_sar",
        "n_pozos_criticos",
        "n_reportes_social",
        "deficit_acui_hm3",
        "latitud",
        "longitud",
        "geom",
    ]
    for c in salud_cols:
        if c not in salud.columns and c != "geom":
            salud[c] = None
    # Evitar FK si dim_colonia aún no está cargada
    salud["id_colonia"] = None
    # NaN → 0 en scores obligatorios (NOT NULL en PostGIS)
    for c in [
        "score_sar_humedad",
        "score_subsidencia",
        "score_abatimiento",
        "score_deficit_acui",
        "score_social",
        "score_severidad_fuga",
    ]:
        salud[c] = pd.to_numeric(salud[c], errors="coerce").fillna(0.0).clip(0, 100)
    salud["n_anomalias_sar"] = pd.to_numeric(salud["n_anomalias_sar"], errors="coerce").fillna(0).astype(int)
    salud["n_pozos_criticos"] = pd.to_numeric(salud["n_pozos_criticos"], errors="coerce").fillna(0).astype(int)
    salud["n_reportes_social"] = pd.to_numeric(salud["n_reportes_social"], errors="coerce").fillna(0).astype(int)

    salud[salud_cols].to_postgis(
        "mapa_salud_red_correlacionado",
        engine,
        schema="zaseva",
        if_exists="append",
        index=False,
    )
    log.info(
        "Persistido run_id=%s · anomalias=%s · score_medio=%.1f",
        run_id,
        len(anom),
        float(salud["score_severidad_fuga"].mean()),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_sar_anomalies(days: int, dry_run: bool) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    meta = {
        "fecha_inicio_ventana": start.isoformat(),
        "fecha_fin_ventana": end.isoformat(),
        "fecha_escena": end.isoformat(),
        "n_escenas": 0,
        "dry_run": dry_run,
    }

    if dry_run:
        log.info("Modo --dry-run: anomalías sintéticas en AOI Poniente.")
        gdf = dry_run_synthetic_anomalies()
        meta["n_escenas"] = 0
        return gdf, meta

    log.info("Descargando Sentinel-1 (últimos %s días) via Earth Engine...", days)
    vv_lin, vh_lin, meta_ee = fetch_sentinel1_patch(days_back=days)
    meta.update(meta_ee)

    vv_f = lee_sigma_filter(vv_lin)
    vh_f = lee_sigma_filter(vh_lin)
    # Índice dieléctrico proxy: combinación VV/VH en dB
    vv_db = linear_to_db(vv_f)
    vh_db = linear_to_db(vh_f)
    combo = 0.6 * vv_db + 0.4 * vh_db

    transform = meta_ee["transform"]
    gdf = detect_moisture_anomalies(combo, transform)
    gdf["polarizacion"] = "VV_VH"
    log.info("Píxeles con humedad anómala: %s", len(gdf))
    return gdf, meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ZASEVA ETL SAR × hidrogeología")
    parser.add_argument("--db-url", default=None, help="Override SUPABASE_DB_URL")
    parser.add_argument("--days", type=int, default=20, help="Ventana Sentinel-1 (10–30)")
    parser.add_argument("--dry-run", action="store_true", help="Sin Earth Engine (sintético)")
    parser.add_argument("--skip-schema", action="store_true", help="No reaplicar DDL")
    parser.add_argument("--skip-ref-load", action="store_true", help="No truncar/recargar acuíferos/pozos")
    args = parser.parse_args(argv)

    days = int(np.clip(args.days, 10, 30))
    run_id = uuid.uuid4()
    log.info("run_id=%s · AOI=%s · days=%s", run_id, AOI_BOUNDS, days)

    db_url = get_db_url(args.db_url)
    engine = create_engine(db_url)

    if not args.skip_schema:
        apply_schema(engine)

    acuiferos = load_acuiferos(engine)
    pozos = load_pozos(engine)
    colonias = load_colonias()
    subsidencia = load_subsidencia(engine)

    if not args.skip_ref_load:
        log.info("Sincronizando acuíferos/pozos de referencia → PostGIS...")
        upsert_reference_layers(engine, acuiferos, pozos)
        # Recargar con pozo_id reales
        pozos = load_pozos(engine)

    sar, meta = build_sar_anomalies(days=days, dry_run=args.dry_run)
    if sar.empty:
        raise SystemExit("No se detectaron anomalías SAR. Prueba --dry-run o amplía --days.")

    log.info("Spatial join con acuíferos, pozos críticos y colonias...")
    enriched = spatial_enrich(sar, acuiferos, pozos, colonias, subsidencia)

    persist_results(engine, run_id, meta, enriched)
    log.info(
        "Listo. Consulta: SELECT * FROM zaseva.vista_diagnostico_alcaldia_resumen;"
    )


if __name__ == "__main__":
    main()
