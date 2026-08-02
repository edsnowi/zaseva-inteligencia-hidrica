"""Construye datamart CDMX para Streamlit ZASEVA.

Salidas en streamlit_app/data/:
  - colonias_cdmx.csv              (catálogo dropdown)
  - colonias_cdmx_simplificado.geojson (polígonos livianos)
  - estres_piezometrico_cdmx.csv
  - oferta_repda_cdmx.csv
  - oferta_repda_cdmx_titulos.csv
  - oferta_acuiferos_cdmx.csv
  - riesgo_sequia_cdmx.csv
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT.parent if ROOT.name == "streamlit_app" else ROOT
DATA_OUT = ROOT / "data"
SRC = AGENT / "data"
UNZIP = AGENT / "unzipped_data"

ALCALDIAS_CDMX = {
    "alvaro obregon",
    "azcapotzalco",
    "benito juarez",
    "coyoacan",
    "cuajimalpa",
    "cuajimalpa de morelos",
    "cuauhtemoc",
    "gustavo a. madero",
    "gustavo a madero",
    "iztacalco",
    "iztapalapa",
    "magdalena contreras",
    "la magdalena contreras",
    "miguel hidalgo",
    "milpa alta",
    "tlahuac",
    "tlalpan",
    "venustiano carranza",
    "xochimilco",
}

PONIENTE = {
    "cuajimalpa",
    "cuajimalpa de morelos",
    "alvaro obregon",
    "miguel hidalgo",
    "magdalena contreras",
    "la magdalena contreras",
}


def _norm(s: str) -> str:
    import unicodedata

    s = str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s


def load_colonias() -> gpd.GeoDataFrame:
    path = SRC / "cdmx" / "colonias_shi.geojson"
    gdf = gpd.read_file(path)
    gdf = gdf[["ID_colonia", "Municipality", "Colonia", "pop", "geometry"]].copy()
    gdf = gdf.rename(
        columns={
            "ID_colonia": "id_colonia",
            "Municipality": "alcaldia",
            "Colonia": "colonia",
            "pop": "poblacion",
        }
    )
    gdf["alcaldia_norm"] = gdf["alcaldia"].map(_norm)
    gdf = gdf[gdf["alcaldia_norm"].isin(ALCALDIAS_CDMX)].copy()
    gdf["colonia"] = gdf["colonia"].astype(str).str.strip().str.title()
    gdf["alcaldia"] = gdf["alcaldia"].astype(str).str.strip().str.title()
    gdf["en_poniente"] = gdf["alcaldia_norm"].isin(PONIENTE)
    gdf["label"] = gdf["colonia"] + " — " + gdf["alcaldia"]
    # centroid for zoom
    pts = gdf.geometry.representative_point()
    gdf["latitud_centro"] = pts.y
    gdf["longitud_centro"] = pts.x
    gdf = gdf.to_crs(4326)
    gdf["geometry"] = gdf.geometry.simplify(0.0003, preserve_topology=True)
    return gdf.reset_index(drop=True)


def trend_piezo(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    pne_cols = [c for c in gdf.columns if c.startswith("PNE_")]
    years = np.array([int(c.split("_")[1]) for c in pne_cols])

    def one(row):
        vals = row[pne_cols].to_numpy(dtype=float)
        mask = ~np.isnan(vals)
        n = int(mask.sum())
        if n < 2:
            return pd.Series(
                {
                    "anio_primero": np.nan,
                    "anio_ultimo": np.nan,
                    "pne_primero_m": np.nan,
                    "pne_ultimo_m": np.nan,
                    "delta_pne_m": np.nan,
                    "tasa_abatimiento_m_anio": np.nan,
                    "n_obs": n,
                }
            )
        y, v = years[mask], vals[mask]
        span = int(y[-1] - y[0])
        delta = float(v[-1] - v[0])
        tasa = float(delta / span) if span else np.nan
        return pd.Series(
            {
                "anio_primero": int(y[0]),
                "anio_ultimo": int(y[-1]),
                "pne_primero_m": float(v[0]),
                "pne_ultimo_m": float(v[-1]),
                "delta_pne_m": delta,
                "tasa_abatimiento_m_anio": tasa,
                "n_obs": n,
            }
        )

    stats = gdf.apply(one, axis=1)
    out = pd.DataFrame(
        {
            "num_pozo": gdf["NUM_POZO"].astype(int),
            "nom_pozo": gdf["NOM_POZO"].astype(str),
            "cve_acui": gdf["CVE_ACUI"].astype(str).str.zfill(4),
            "nom_acuif": gdf["NOM_ACUIF"].astype(str),
            "nom_edo": gdf["NOM_EDO"].astype(str),
            "latitud": gdf["LATITUD"].astype(float),
            "longitud": gdf["LONGITUD"].astype(float),
        }
    )
    out = pd.concat([out.reset_index(drop=True), stats.reset_index(drop=True)], axis=1)

    def nivel(tasa, n_obs):
        if n_obs < 2 or pd.isna(tasa):
            return "SIN_SERIE"
        if tasa >= 1.0:
            return "ALTO"
        if tasa >= 0.3:
            return "MEDIO"
        if tasa >= 0:
            return "LEVE"
        return "RECUPERACION_O_ESTABLE"

    out["nivel_estres"] = [
        nivel(t, n) for t, n in zip(out["tasa_abatimiento_m_anio"], out["n_obs"])
    ]
    return out


def spatial_join_colonias(points: pd.DataFrame, colonias: gpd.GeoDataFrame) -> pd.DataFrame:
    gdf = gpd.GeoDataFrame(
        points.copy(),
        geometry=gpd.points_from_xy(points["longitud"], points["latitud"]),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(
        gdf,
        colonias[["id_colonia", "colonia", "alcaldia", "en_poniente", "label", "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.drop(columns=["index_right", "geometry"], errors="ignore")
    # si un punto cae en borde y duplica, nos quedamos con uno
    key = "num_pozo" if "num_pozo" in joined.columns else "titulo"
    joined = joined.drop_duplicates(subset=[key], keep="first")
    return joined.reset_index(drop=True)


def main() -> None:
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    print("1) Colonias CDMX...")
    colonias = load_colonias()
    print("   ", len(colonias), "colonias")
    cat = colonias[
        ["id_colonia", "colonia", "alcaldia", "en_poniente", "label", "latitud_centro", "longitud_centro", "poblacion"]
    ].sort_values(["alcaldia", "colonia"])
    cat.to_csv(DATA_OUT / "colonias_cdmx.csv", index=False)
    # geojson liviano solo attrs útiles
    colonias[
        ["id_colonia", "colonia", "alcaldia", "en_poniente", "label", "geometry"]
    ].to_file(DATA_OUT / "colonias_cdmx_simplificado.geojson", driver="GeoJSON")

    print("2) Acuíferos que tocan CDMX...")
    acu = gpd.read_file(UNZIP / "disponibilidad_de_agua_subterranea_09-11-2023.shp").to_crs(4326)
    acu["CLV_ACUI"] = acu["CLV_ACUI"].astype(str).str.zfill(4)
    cdmx_union = colonias.unary_union
    acu_cdmx = acu[acu.intersects(cdmx_union)].copy()
    oferta = pd.DataFrame(
        {
            "cve_acui": acu_cdmx["CLV_ACUI"],
            "nom_acui": acu_cdmx["NOM_ACUI"].astype(str),
            "nom_edo": acu_cdmx["NOM_EDO"].astype(str),
            "recarga_to_hm3": acu_cdmx["RECARGA_TO"].astype(float),
            "descarga_n_hm3": acu_cdmx["DESCARGA_N"].astype(float),
            "dma_negati_hm3": acu_cdmx["DMA_NEGATI"].astype(float),
            "deficit_hm3": acu_cdmx["DMA_NEGATI"].astype(float).abs(),
        }
    )
    oferta.to_csv(DATA_OUT / "oferta_acuiferos_cdmx.csv", index=False)
    print("   acuíferos:", len(oferta), oferta["cve_acui"].tolist())

    print("3) Piezometría en CDMX...")
    piezo_shp = gpd.read_file(UNZIP / "red_piezometrica" / "red_piezometrica_2025.shp")
    # candidatos: entidad DF/CDMX o dentro del polígono CDMX
    piezo_shp["CVE_EDO"] = piezo_shp["CVE_EDO"].astype(str).str.zfill(2)
    cand = piezo_shp[
        (piezo_shp["CVE_EDO"] == "09")
        | (piezo_shp["NOM_EDO"].str.contains("CIUDAD|DISTRITO|MEXICO", case=False, na=False))
    ].copy()
    # también por spatial filter amplio
    all_pts = gpd.GeoDataFrame(
        piezo_shp,
        geometry=gpd.points_from_xy(piezo_shp["LONGITUD"], piezo_shp["LATITUD"]),
        crs="EPSG:4326",
    )
    inside = all_pts[all_pts.within(cdmx_union)].copy()
    # union by NUM_POZO
    ids = set(cand["NUM_POZO"]).union(set(inside["NUM_POZO"]))
    piezo_f = piezo_shp[piezo_shp["NUM_POZO"].isin(ids)].copy()
    piezo = trend_piezo(piezo_f)
    piezo = spatial_join_colonias(piezo, colonias)
    # solo puntos que cayeron en alguna colonia CDMX
    piezo = piezo[piezo["colonia"].notna()].copy()
    piezo["en_bbox_piloto"] = piezo["en_poniente"].fillna(False)
    piezo.to_csv(DATA_OUT / "estres_piezometrico_cdmx.csv", index=False)
    print("   pozos con colonia:", len(piezo))

    print("4) REPDA en CDMX...")
    repda = pd.read_csv(SRC / "anexos_sub_06_2025.csv")
    repda = repda.rename(
        columns={
            "TITULO": "titulo",
            "LAT": "latitud",
            "LON": "longitud",
            "VOL": "volumen_m3_anio",
            "TITULAR": "titular",
            "USO": "uso",
            "FECHA": "fecha_titulo",
        }
    )
    repda = repda.dropna(subset=["latitud", "longitud", "volumen_m3_anio"])
    # prefiltro bbox CDMX
    repda = repda[
        repda["longitud"].between(-99.37, -98.94) & repda["latitud"].between(19.04, 19.60)
    ].copy()
    repda["volumen_hm3_anio"] = repda["volumen_m3_anio"] / 1_000_000.0
    repda = spatial_join_colonias(repda, colonias)
    repda = repda[repda["colonia"].notna()].copy()
    repda["en_bbox_piloto"] = repda["en_poniente"].fillna(False)
    # puntos únicos titulo+coords
    repda = repda.drop_duplicates(subset=["titulo", "latitud", "longitud"]).reset_index(drop=True)
    n_pts = repda.groupby("titulo")["titulo"].transform("count")
    repda["volumen_punto_m3_anio"] = repda["volumen_m3_anio"] / n_pts
    repda["volumen_punto_hm3_anio"] = repda["volumen_punto_m3_anio"] / 1_000_000.0
    repda.to_csv(DATA_OUT / "oferta_repda_cdmx.csv", index=False)
    titles = (
        repda.sort_values(["titulo", "latitud"])
        .drop_duplicates("titulo")[
            [
                "titulo",
                "titular",
                "uso",
                "volumen_m3_anio",
                "volumen_hm3_anio",
                "fecha_titulo",
                "colonia",
                "alcaldia",
                "en_poniente",
            ]
        ]
        .reset_index(drop=True)
    )
    titles.to_csv(DATA_OUT / "oferta_repda_cdmx_titulos.csv", index=False)
    print("   puntos REPDA:", len(repda), "títulos:", len(titles))

    print("5) Sequía alcaldías CDMX...")
    seq_path = AGENT / "riesgo_sequia_poniente.csv"
    # prefer full municipal file if available
    full = AGENT / "sequia_municipal_enero_8ee9.csv"
    if full.exists():
        seq = pd.read_csv(full)
        seq["cve_ent"] = seq["cve_ent"].astype(str).str.zfill(2)
        seq = seq[seq["cve_ent"] == "09"].copy()
        seq["cve_geo"] = seq["cve_ent"] + seq["cve_mun"].astype(str).str.zfill(3)
        sps = next(c for c in seq.columns if c.startswith("sps_"))
        msm = next(c for c in seq.columns if c.startswith("msm_"))
        ahorro = next(c for c in seq.columns if c.startswith("ahorro_"))
        out = pd.DataFrame(
            {
                "cve_geo": seq["cve_geo"],
                "nombre_mun": seq["nombre_mun"],
                "entidad": seq["entidad"],
                "sps": seq[sps],
                "msm": seq[msm],
                "ahorro_uso_eficiente": seq[ahorro],
                "fecha_corte": sps.replace("sps_", ""),
            }
        )
    elif seq_path.exists():
        out = pd.read_csv(seq_path)
    else:
        out = pd.DataFrame()
    out.to_csv(DATA_OUT / "riesgo_sequia_cdmx.csv", index=False)
    print("   municipios sequía:", len(out))

    # compat: también copiar nombres "piloto" apuntando a CDMX para no romper loaders viejos
    # (la app nueva usará *_cdmx)
    print("OK ->", DATA_OUT)


if __name__ == "__main__":
    main()
