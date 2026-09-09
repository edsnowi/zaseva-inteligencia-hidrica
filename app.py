"""
ZASEVA — Centro de Inteligencia Hídrica (CDMX)
Fase A + ampliación CDMX: textos legibles, vista piperos, dropdown de colonias.
Lee CSV locales y, si hay SUPABASE_DB_URL, también vistas PostGIS (SAR / diagnóstico).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
import pydeck as pdk

DATA_DIR = Path(__file__).resolve().parent / "data"

st.set_page_config(
    page_title="ZASEVA · Inteligencia Hídrica",
    page_icon="💧",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.05rem; }
      h1, h2, h3 { font-family: Georgia, serif; color: #0b3c4d; }
      div[data-testid="stMetricValue"] { color: #0b3c4d; }
      .hint { color: #4a5c63; font-size: 0.92rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def semaforo_piezo(nivel: str) -> str:
    n = str(nivel).upper() if pd.notna(nivel) else ""
    if n == "ALTO":
        return "🔴 Crítico"
    if n == "MEDIO":
        return "🟠 Medio"
    if n == "LEVE":
        return "🟡 Leve"
    if n == "RECUPERACION_O_ESTABLE":
        return "🟢 Estable / recuperación"
    return "⚪ Sin serie suficiente"


def consejo_pipero(nivel: str) -> str:
    n = str(nivel).upper() if pd.notna(nivel) else ""
    if n == "ALTO":
        return "Evitar si hay alternativa cerca"
    if n == "MEDIO":
        return "Usar con precaución"
    if n == "LEVE":
        return "Aceptable"
    if n == "RECUPERACION_O_ESTABLE":
        return "Preferible (menos estrés)"
    return "Dato insuficiente"


def get_db_url() -> str | None:
    """URI de Supabase desde Secrets (Cloud) o variable de entorno (local)."""
    url = None
    try:
        url = st.secrets.get("SUPABASE_DB_URL")  # type: ignore[attr-defined]
    except Exception:
        url = None
    if not url:
        url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        return None
    # Limpiar saltos de línea del recuadro de Secrets y espacios
    cleaned = (
        str(url)
        .replace("\r", "")
        .replace("\n", "")
        .replace(" ", "")
        .strip()
        .strip('"')
        .strip("'")
    )
    if not cleaned:
        return None
    # Supabase / Streamlit Cloud suelen requerir SSL
    if "sslmode=" not in cleaned.lower():
        sep = "&" if "?" in cleaned else "?"
        cleaned = f"{cleaned}{sep}sslmode=require"
    return cleaned


@st.cache_data(ttl=300)
def load_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_data(ttl=60)
def load_sql(query: str) -> pd.DataFrame:
    """Lee una consulta SQL desde Supabase. Vacío si no hay URL o falla."""
    df, _err = load_sql_status(query)
    return df


@st.cache_data(ttl=60)
def load_sql_status(query: str) -> tuple[pd.DataFrame, str]:
    """Como load_sql, pero también devuelve el error (si hubo)."""
    url = get_db_url()
    if not url:
        return pd.DataFrame(), "Sin SUPABASE_DB_URL"
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            return pd.read_sql(text(query), conn), ""
    except Exception as exc:
        return pd.DataFrame(), str(exc)


@st.cache_data(ttl=60)
def probe_supabase() -> dict:
    """Prueba de conexión + conteo SAR para diagnóstico en pantalla."""
    url = get_db_url()
    if not url:
        return {"ok": False, "error": "Sin SUPABASE_DB_URL", "sar_n": 0, "salud_n": 0}
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            sar_n = int(conn.execute(text(
                "SELECT COUNT(*) FROM zaseva.anomalias_satelitales_sar WHERE humedad_anomala = TRUE"
            )).scalar() or 0)
            salud_n = int(conn.execute(text(
                "SELECT COUNT(*) FROM zaseva.mapa_salud_red_correlacionado"
            )).scalar() or 0)
            diag_n = int(conn.execute(text(
                "SELECT COUNT(*) FROM zaseva.vista_diagnostico_alcaldia_resumen"
            )).scalar() or 0)
        return {"ok": True, "error": "", "sar_n": sar_n, "salud_n": salud_n, "diag_n": diag_n}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "sar_n": 0, "salud_n": 0, "diag_n": 0}


@st.cache_data(ttl=300)
def load_colonias_geo() -> pd.DataFrame:
    """Devuelve geojson como records mínimos vía geopandas si existe; si no, vacío."""
    path = DATA_DIR / "colonias_cdmx_simplificado.geojson"
    if not path.exists():
        return pd.DataFrame()
    import geopandas as gpd

    gdf = gpd.read_file(path)
    return gdf


def prepare_piezo(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "cve_acui" in out.columns:
        out["cve_acui"] = out["cve_acui"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    out["semaforo"] = out.get("nivel_estres", pd.Series(dtype=str)).map(semaforo_piezo)
    out["consejo_para_piperos"] = out.get("nivel_estres", pd.Series(dtype=str)).map(consejo_pipero)
    if "num_pozo" in out.columns:
        out["num_pozo"] = pd.to_numeric(out["num_pozo"], errors="coerce")
    if "colonia" not in out.columns:
        out["colonia"] = out.get("nom_pozo", pd.Series([""] * len(out))).fillna("").astype(str)
    if "alcaldia" not in out.columns:
        out["alcaldia"] = ""
    if "en_poniente" in out.columns:
        out["en_poniente"] = out["en_poniente"].astype(str).str.lower().isin(["true", "1", "yes"])
    elif "en_bbox_piloto" in out.columns:
        out["en_poniente"] = out["en_bbox_piloto"].astype(str).str.lower().isin(["true", "1", "yes"])
    return out


def piezo_table_view(df: pd.DataFrame, include_coords: bool = False) -> pd.DataFrame:
    """Arma tabla de pozos solo con columnas disponibles."""
    rename = {
        "num_pozo": "No. pozo",
        "colonia": "Colonia",
        "alcaldia": "Alcaldía",
        "semaforo": "Semáforo",
        "tasa_abatimiento_m_anio": "Bajada (m/año)" if not include_coords else "Bajada del nivel (m/año)",
        "consejo_para_piperos": "Consejo",
        "latitud": "Latitud",
        "longitud": "Longitud",
    }
    wanted = ["num_pozo", "colonia", "alcaldia", "semaforo", "tasa_abatimiento_m_anio", "consejo_para_piperos"]
    if include_coords:
        wanted.extend(["latitud", "longitud"])
    cols = [c for c in wanted if c in df.columns]
    if not cols:
        return pd.DataFrame()
    return df[cols].rename(columns={k: v for k, v in rename.items() if k in cols})


def assign_alcaldia_to_points(points: pd.DataFrame, colonias: pd.DataFrame) -> pd.DataFrame:
    """Asigna alcaldía a puntos SAR por colonia más cercana (centroide)."""
    if points.empty or colonias.empty:
        out = points.copy()
        if "alcaldia" not in out.columns:
            out["alcaldia"] = "Sin asignar"
        return out
    if "alcaldia" in points.columns and points["alcaldia"].notna().any():
        out = points.copy()
        out["alcaldia"] = out["alcaldia"].fillna("Sin asignar").astype(str)
        return out
    need = {"latitud", "longitud"}.issubset(points.columns)
    cneed = {"latitud_centro", "longitud_centro", "alcaldia"}.issubset(colonias.columns)
    if not need or not cneed:
        out = points.copy()
        out["alcaldia"] = "Sin asignar"
        return out

    pts = points.dropna(subset=["latitud", "longitud"]).copy()
    cols = colonias.dropna(subset=["latitud_centro", "longitud_centro", "alcaldia"]).copy()
    if pts.empty or cols.empty:
        out = points.copy()
        out["alcaldia"] = "Sin asignar"
        return out

    # Vecino más cercano en grados (suficiente para asignación a alcaldía)
    c_lat = cols["latitud_centro"].to_numpy()
    c_lon = cols["longitud_centro"].to_numpy()
    c_alc = cols["alcaldia"].astype(str).to_numpy()
    assigned = []
    for lat, lon in zip(pts["latitud"].to_numpy(), pts["longitud"].to_numpy()):
        d2 = (c_lat - lat) ** 2 + (c_lon - lon) ** 2
        assigned.append(c_alc[int(d2.argmin())])
    pts = pts.copy()
    pts["alcaldia"] = assigned
    return pts



def filter_points_by_alcaldias(
    points: pd.DataFrame,
    colonias: pd.DataFrame,
    alcaldias: list[str] | None,
    pad: float = 0.02,
) -> pd.DataFrame:
    """Filtra puntos por nombre de alcaldía o, si no hay match útil, por bbox de colonias."""
    if points.empty or not alcaldias:
        return points
    out = points.copy()
    if "alcaldia" in out.columns:
        by_name = out[out["alcaldia"].astype(str).isin(alcaldias)]
        # Exigir que el match por nombre recupere una fracción razonable
        min_keep = max(3, int(0.05 * len(out))) if len(out) >= 20 else 1
        if len(by_name) >= min_keep:
            return by_name
    # Fallback geográfico (o devolver todo si no hay colonias)
    if colonias.empty or not {"alcaldia", "latitud_centro", "longitud_centro"}.issubset(colonias.columns):
        return out
    if not {"latitud", "longitud"}.issubset(out.columns):
        return out
    foc = colonias[colonias["alcaldia"].isin(alcaldias)].dropna(subset=["latitud_centro", "longitud_centro"])
    if foc.empty:
        return out
    lat_min, lat_max = float(foc["latitud_centro"].min()) - pad, float(foc["latitud_centro"].max()) + pad
    lon_min, lon_max = float(foc["longitud_centro"].min()) - pad, float(foc["longitud_centro"].max()) + pad
    geo = out[
        (out["latitud"] >= lat_min)
        & (out["latitud"] <= lat_max)
        & (out["longitud"] >= lon_min)
        & (out["longitud"] <= lon_max)
    ]
    # Si el bbox también deja 0 pero había puntos, no borrar la capa entera
    return geo if len(geo) else out



def nearest_points_text(
    lat: float,
    lon: float,
    pool: pd.DataFrame,
    n: int = 3,
    label_col: str = "num_pozo",
) -> str:
    """Texto corto con los N puntos más cercanos (aprox. en grados)."""
    if pool.empty or not {"latitud", "longitud"}.issubset(pool.columns):
        return "Sin vecinos cercanos"
    df = pool.dropna(subset=["latitud", "longitud"]).copy()
    if df.empty:
        return "Sin vecinos cercanos"
    d2 = (df["latitud"] - lat) ** 2 + (df["longitud"] - lon) ** 2
    # excluir el mismo punto si coincide (no usar columna "_d2": itertuples la omite)
    df = df.loc[d2 > 1e-12].copy()
    if df.empty:
        return "Sin vecinos cercanos"
    df["dist_km"] = (d2.loc[df.index] ** 0.5) * 111.0
    top = df.nsmallest(n, "dist_km")
    parts = []
    for _, row in top.iterrows():
        lab = row.get(label_col)
        alc = str(row.get("alcaldia") or "").strip()
        dist_km = float(row["dist_km"])
        if lab is not None and pd.notna(lab):
            parts.append(f"#{int(lab)} {alc} (~{dist_km:.1f} km)".strip())
        else:
            parts.append(f"{alc} (~{dist_km:.1f} km)".strip() if alc else f"(~{dist_km:.1f} km)")
    return " | ".join(parts)


def enrich_critical_wells(piezo_df: pd.DataFrame) -> pd.DataFrame:
    """Tabla operativa de pozos ALTO + pozo preferible más cercano."""
    if piezo_df.empty or "nivel_estres" not in piezo_df.columns:
        return pd.DataFrame()
    crit = piezo_df[piezo_df["nivel_estres"].astype(str).str.upper() == "ALTO"].copy()
    if crit.empty:
        return crit
    pref = piezo_df[
        piezo_df["nivel_estres"].astype(str).str.upper().isin(["LEVE", "RECUPERACION_O_ESTABLE"])
    ].copy()
    recs = []
    dists = []
    for r in crit.itertuples():
        if pref.empty or not pd.notna(getattr(r, "latitud", None)):
            recs.append("Sin alternativa cercana")
            dists.append(pd.NA)
            continue
        d2 = (pref["latitud"] - r.latitud) ** 2 + (pref["longitud"] - r.longitud) ** 2
        j = int(d2.to_numpy().argmin())
        row = pref.iloc[j]
        dist_km = float(d2.iloc[j] ** 0.5) * 111.0
        recs.append(
            f"Pozo {int(row['num_pozo'])} · {row.get('colonia', '')} · {row.get('alcaldia', '')} (~{dist_km:.1f} km)"
        )
        dists.append(round(dist_km, 2))
    crit = crit.copy()
    crit["recomendacion_cercana"] = recs
    crit["dist_recomendacion_km"] = dists
    return crit.sort_values("tasa_abatimiento_m_anio", ascending=False)


def humedad_por_alcaldia(

    sar: pd.DataFrame,
    salud: pd.DataFrame,
    diagnostico: pd.DataFrame,
    colonias: pd.DataFrame,
    alcaldias_filtro: list[str] | None = None,
) -> pd.DataFrame:
    """
    Tabla comercial: humedades anómalas (fugas invisibles proxy) por alcaldía/municipio.

    Prioridad: contar puntos SAR reales (los del mapa). Score/riesgo se cruzan
    desde la vista B2G o mapa_salud si existen.
    """
    out = pd.DataFrame(columns=["alcaldia", "humedades_anomalas", "score_severidad_max", "nivel_riesgo_estructural"])

    # 1) Conteo real desde SAR (misma fuente que los círculos morados)
    if len(sar) and {"latitud", "longitud"}.issubset(sar.columns):
        tagged = sar.copy()
        if "alcaldia" not in tagged.columns or tagged["alcaldia"].isna().all():
            tagged = assign_alcaldia_to_points(tagged, colonias)
        tagged = tagged[tagged["alcaldia"].astype(str).str.strip().isin(["", "nan", "None", "Sin asignar"]) == False]
        if len(tagged):
            out = (
                tagged.groupby("alcaldia", dropna=False)
                .size()
                .reset_index(name="humedades_anomalas")
            )
            out["score_severidad_max"] = pd.NA
            out["nivel_riesgo_estructural"] = pd.NA

    # 2) Si no hubo SAR, usar vista diagnóstico (solo si trae conteos > 0)
    if out.empty and len(diagnostico) and "alcaldia" in diagnostico.columns and "puntos_criticos_fugas" in diagnostico.columns:
        tmp = diagnostico[["alcaldia", "puntos_criticos_fugas"]].copy()
        tmp = tmp.rename(columns={"puntos_criticos_fugas": "humedades_anomalas"})
        if int(pd.to_numeric(tmp["humedades_anomalas"], errors="coerce").fillna(0).sum()) > 0:
            out = tmp
            if "score_severidad_max" in diagnostico.columns:
                out["score_severidad_max"] = diagnostico["score_severidad_max"].values
            if "nivel_riesgo_estructural" in diagnostico.columns:
                out["nivel_riesgo_estructural"] = diagnostico["nivel_riesgo_estructural"].values

    # 3) Último recurso: mapa_salud
    if out.empty and len(salud) and "alcaldia" in salud.columns:
        out = (
            salud.dropna(subset=["alcaldia"])
            .groupby("alcaldia", dropna=False)
            .agg(
                humedades_anomalas=("score_severidad_fuga", "count"),
                score_severidad_max=("score_severidad_fuga", "max"),
            )
            .reset_index()
        )
        out["nivel_riesgo_estructural"] = out["score_severidad_max"].map(
            lambda s: "CRITICO" if s >= 75 else "ALTO" if s >= 50 else "MEDIO" if s >= 25 else "BAJO"
        )

    if out.empty:
        return pd.DataFrame(
            columns=["alcaldia", "humedades_anomalas", "score_severidad_max", "nivel_riesgo_estructural", "prioridad"]
        )

    # Cruzar score/riesgo de la vista B2G si hace falta
    if len(diagnostico) and "alcaldia" in diagnostico.columns:
        meta = diagnostico.copy()
        keep = [c for c in ["alcaldia", "score_severidad_max", "nivel_riesgo_estructural"] if c in meta.columns]
        if len(keep) > 1:
            meta = meta[keep].drop_duplicates("alcaldia")
            out = out.merge(meta, on="alcaldia", how="left", suffixes=("", "_diag"))
            if "score_severidad_max_diag" in out.columns:
                out["score_severidad_max"] = out["score_severidad_max"].fillna(out["score_severidad_max_diag"])
                out = out.drop(columns=["score_severidad_max_diag"])
            if "nivel_riesgo_estructural_diag" in out.columns:
                out["nivel_riesgo_estructural"] = out["nivel_riesgo_estructural"].fillna(
                    out["nivel_riesgo_estructural_diag"]
                )
                out = out.drop(columns=["nivel_riesgo_estructural_diag"])

    # Si aún no hay score, aproximar con mapa_salud
    if out["score_severidad_max"].isna().all() and len(salud) and "alcaldia" in salud.columns and "score_severidad_fuga" in salud.columns:
        sc = (
            salud.dropna(subset=["alcaldia"])
            .groupby("alcaldia")["score_severidad_fuga"]
            .max()
            .reset_index(name="score_severidad_max")
        )
        out = out.drop(columns=["score_severidad_max"], errors="ignore").merge(sc, on="alcaldia", how="left")

    if "nivel_riesgo_estructural" not in out.columns or out["nivel_riesgo_estructural"].isna().all():
        out["nivel_riesgo_estructural"] = pd.to_numeric(out.get("score_severidad_max"), errors="coerce").map(
            lambda s: (
                "CRITICO" if pd.notna(s) and s >= 75
                else "ALTO" if pd.notna(s) and s >= 50
                else "MEDIO" if pd.notna(s) and s >= 25
                else "BAJO" if pd.notna(s)
                else "REVISAR"
            )
        )

    if alcaldias_filtro:
        # No descartar filas SAR si el nombre no matchea el filtro; filtrar solo si hay overlap
        matched = out[out["alcaldia"].isin(alcaldias_filtro)]
        if len(matched):
            out = matched

    out["humedades_anomalas"] = pd.to_numeric(out["humedades_anomalas"], errors="coerce").fillna(0).astype(int)
    out = out.sort_values("humedades_anomalas", ascending=False)

    def _prio(n: int) -> str:
        if n >= 200:
            return "URGENTE — alta densidad de señales"
        if n >= 50:
            return "ALTA — conviene inspección"
        if n >= 10:
            return "MEDIA — monitorear"
        if n >= 1:
            return "BAJA — señales puntuales"
        return "SIN SEÑALES SAR"

    out["prioridad"] = out["humedades_anomalas"].map(_prio)
    return out.reset_index(drop=True)


def load_dashboard_layers() -> dict:
    """
    Carga capas del dashboard.
    Preferencia: PostGIS (si hay secret) → CSV local como respaldo.
    """
    fuente = "CSV local"
    db_ok = bool(get_db_url())

    oferta = load_sql(
        "SELECT cve_acui, nom_acui, nom_edo, recarga_hm3 AS recarga_to_hm3, deficit_hm3 "
        "FROM zaseva.acuiferos_conagua"
    )
    if oferta.empty:
        oferta = load_sql(
            "SELECT cve_acui, nom_acui, nom_edo, recarga_to_hm3, deficit_hm3 "
            "FROM zaseva.v_oferta_acuifero"
        )
    if oferta.empty:
        oferta = load_csv("oferta_acuiferos_cdmx.csv")
        if oferta.empty:
            oferta = load_csv("oferta_acuiferos_poniente.csv")
            if "CLV_ACUI" in oferta.columns:
                oferta = oferta.rename(
                    columns={
                        "CLV_ACUI": "cve_acui",
                        "NOM_ACUI": "nom_acui",
                        "NOM_EDO": "nom_edo",
                        "RECARGA_TO": "recarga_to_hm3",
                        "DMA_NEGATI": "dma_negati_hm3",
                    }
                )
                oferta["deficit_hm3"] = oferta["dma_negati_hm3"].abs()

    piezo = load_sql(
        """
        SELECT num_pozo, nom_pozo, cve_acui, nom_acui AS nom_acuif,
               latitud, longitud, tasa_abatimiento_m_anio, pne_ultimo_m,
               nivel_estres, en_bbox_piloto,
               COALESCE(en_bbox_piloto, FALSE) AS en_poniente,
               2 AS n_obs
        FROM zaseva.pozos_piezometricos
        """
    )
    if piezo.empty:
        piezo = load_sql(
            """
            SELECT num_pozo, nom_pozo, cve_acui, nom_acuif, latitud, longitud,
                   tasa_abatimiento_m_anio, pne_ultimo_m, n_obs, nivel_estres,
                   en_bbox_piloto, en_bbox_piloto AS en_poniente
            FROM zaseva.v_heatmap_piezometria
            """
        )
    if piezo.empty:
        piezo = load_csv("estres_piezometrico_cdmx.csv")
        if piezo.empty:
            piezo = load_csv("estres_piezometrico_poniente.csv")

    repda = load_sql(
        """
        SELECT titulo, titular, uso, volumen_m3_anio, volumen_hm3_anio,
               volumen_punto_m3_anio, volumen_punto_hm3_anio,
               latitud, longitud, cve_acui, nom_acui, en_bbox_piloto,
               en_bbox_piloto AS en_poniente
        FROM zaseva.v_repda_poniente
        """
    )
    if repda.empty:
        repda = load_csv("oferta_repda_cdmx.csv")
        if repda.empty:
            repda = load_csv("oferta_repda_poniente.csv")

    titles = load_csv("oferta_repda_cdmx_titulos.csv")
    if titles.empty:
        titles = load_csv("oferta_repda_poniente_titulos.csv")

    sequia = load_csv("riesgo_sequia_cdmx.csv")
    if sequia.empty:
        sequia = load_csv("riesgo_sequia_poniente.csv")

    sar, sar_err = load_sql_status(
        """
        SELECT anomalia_id, fecha_escena, polarizacion, backscatter_db, delta_db,
               humedad_anomala, cve_acui, latitud, longitud, dist_pozo_critico_m
        FROM zaseva.anomalias_satelitales_sar
        WHERE humedad_anomala = TRUE
        ORDER BY fecha_escena DESC
        LIMIT 5000
        """
    )
    diagnostico = load_sql(
        """
        SELECT alcaldia, puntos_criticos_fugas, deficit_acuifero_hm3_promedio,
               score_severidad_promedio, score_severidad_max, nivel_riesgo_estructural, n_colonias
        FROM zaseva.vista_diagnostico_alcaldia_resumen
        ORDER BY score_severidad_max DESC NULLS LAST
        """
    )
    salud = load_sql(
        """
        SELECT colonia, alcaldia, cve_acui, score_severidad_fuga, nivel_riesgo_red,
               score_sar_humedad, score_abatimiento, deficit_acui_hm3,
               latitud, longitud, fecha_calculo
        FROM zaseva.mapa_salud_red_correlacionado
        ORDER BY score_severidad_fuga DESC
        LIMIT 3000
        """
    )

    if db_ok and (not sar.empty or not diagnostico.empty or not salud.empty or not oferta.empty):
        fuente = "Supabase + CSV"
    elif db_ok:
        fuente = "CSV local (Supabase configurado, sin filas SAR aún)"

    return {
        "oferta": oferta,
        "piezo": prepare_piezo(piezo),
        "repda": repda,
        "titles": titles,
        "sequia": sequia,
        "sar": sar,
        "sar_err": sar_err,
        "diagnostico": diagnostico,
        "salud": salud,
        "fuente": fuente,
        "db_ok": db_ok,
    }


def main() -> None:
    st.title("ZASEVA")
    st.subheader("Centro de Inteligencia Hídrica — Ciudad de México")
    st.markdown(
        """
        <p class="hint">
        Mapa de <b>riesgo hídrico</b> con datos oficiales (CONAGUA / REPDA) para CDMX,
        más capa satelital Sentinel-1 (fugas invisibles / humedad anómala) cuando Supabase está conectado.
        Puedes filtrar al <b>Corredor Poniente</b> o buscar por <b>colonia</b>.
        </p>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("¿Qué estoy viendo? (guía rápida)", expanded=False):
        st.markdown(
            """
            - **Déficit de acuíferos:** el subsuelo en números rojos.
            - **Semáforo de pozos:** qué tan rápido baja el nivel del agua.
            - **REPDA:** agua autorizada legalmente (no bombeo en vivo).
            - **SAR / fugas invisibles:** humedad anómala detectada con radar Sentinel-1.
            - **Score de severidad:** cruce satélite + pozos + déficit (0–100) para plática B2G.
            - **Para piperos:** guía de zonas preferibles vs a evitar (proxy de estrés, no tanque lleno).
            """
        )

    # ---- Datos (Supabase si hay secret; si no, CSV) ----
    layers = load_dashboard_layers()
    oferta = layers["oferta"]
    piezo = layers["piezo"]
    repda = layers["repda"]
    titles = layers["titles"]
    sequia = layers["sequia"]
    sar = layers["sar"]
    sar_err = layers.get("sar_err", "")
    diagnostico = layers["diagnostico"]
    salud = layers["salud"]
    fuente = layers["fuente"]
    db_ok = layers["db_ok"]

    if db_ok:
        probe = probe_supabase()
        if probe["ok"]:
            st.caption(
                f"Fuente de datos: **{fuente}** · Supabase conectado · "
                f"SAR en BD={probe['sar_n']} · cargados al mapa={len(sar)} · "
                f"salud={probe['salud_n']} · diagnóstico={probe.get('diag_n', 0)}"
            )
            if probe["sar_n"] > 0 and sar.empty:
                st.error(
                    "La base tiene puntos SAR, pero la consulta del mapa no trajo filas. "
                    "Revisa el error abajo (posible columna faltante o cache vieja)."
                )
                if sar_err:
                    with st.expander("Error al cargar SAR"):
                        st.code(sar_err[:1500])
            elif probe["sar_n"] == 0:
                st.warning(
                    "Supabase está conectado pero la tabla de humedad anómala está vacía "
                    "(0 filas). Hay que volver a correr el ETL Sentinel-1."
                )
        else:
            st.error(
                "Hay `SUPABASE_DB_URL`, pero **la base no responde**. "
                "Sin esa conexión no hay puntos morados (SAR solo vive en Supabase; pozos/REPDA sí salen del CSV)."
            )
            err = (probe.get("error") or "").strip()
            if err:
                st.code(err[:1200])
            st.markdown(
                """
                **Cómo arreglarlo (2 minutos):**
                1. Supabase → tu proyecto → **Connect** → **URI** (Session pooler o Direct).
                2. Pega la URI con tu contraseña real (sin `[YOUR-PASSWORD]`).
                3. Streamlit Cloud → **Settings → Secrets** → reemplaza `SUPABASE_DB_URL` completo.
                4. **Reboot app**.

                Si el error dice `tenant/user ... not found`, la URI es de otro proyecto o el pooler
                ya no reconoce ese `postgres.xxxxx` — genera una URI nueva desde Connect.
                """
            )
    else:
        st.caption(
            "Fuente de datos: **CSV local**. "
            "Para activar satélite/diagnóstico: configura `SUPABASE_DB_URL` en Streamlit Secrets."
        )
    if sar_err and not sar.empty:
        st.caption(f"Nota SAR: {sar_err[:200]}")

    colonias = load_csv("colonias_cdmx.csv")
    colonias_geo = load_colonias_geo()
    # Asignar alcaldía a puntos SAR (para filtrar y contar por gobernación)
    sar = assign_alcaldia_to_points(sar, colonias)
    sar_bruto = sar.copy()  # antes de filtros de ámbito/alcaldía
    if len(salud) and "alcaldia" in salud.columns:
        # Si mapa_salud ya trae alcaldía, preferirla en puntos cercanos vía merge simple no aplica;
        # el assign por colonia cubre el caso SAR crudo.
        pass

    # ---- Filtros ----
    ambito = st.selectbox(
        "Ámbito geográfico",
        ["Toda la CDMX", "Corredor Poniente"],
        help="Poniente = Cuajimalpa, Álvaro Obregón, Miguel Hidalgo y Magdalena Contreras.",
    )

    # catálogo base por ámbito
    col_cat = colonias.copy()
    pie = piezo.copy()
    rep = repda.copy()
    sar_map = sar.copy()
    salud_map = salud.copy()
    if ambito == "Corredor Poniente":
        if "en_poniente" in col_cat.columns:
            col_cat = col_cat[col_cat["en_poniente"] == True]  # noqa: E712
        if "en_poniente" in pie.columns:
            pie = pie[pie["en_poniente"] == True]  # noqa: E712
        if "en_poniente" in rep.columns:
            rep = rep[rep["en_poniente"] == True]  # noqa: E712
        elif "en_bbox_piloto" in pie.columns:
            pie = pie[pie["en_bbox_piloto"] == True]  # noqa: E712
        if len(sar_map) and {"latitud", "longitud"}.issubset(sar_map.columns):
            sar_map = sar_map[
                (sar_map["longitud"] >= -99.31)
                & (sar_map["longitud"] <= -99.15)
                & (sar_map["latitud"] >= 19.30)
                & (sar_map["latitud"] <= 19.45)
            ]

    st.caption(
        "En México a estos barrios se les dice **colonias** (también hay fraccionamientos, pueblos o unidades habitacionales). "
        "En esta app usamos **Colonia** porque es el nombre más común y el que entiende casi todo el mundo."
    )

    alc_all = sorted(col_cat["alcaldia"].dropna().unique().tolist()) if len(col_cat) else []
    c_alc, c_col = st.columns(2)

    with c_alc:
        st.markdown("#### Alcaldías")
        alc_todo = st.checkbox("Seleccionar todas las alcaldías", value=True, key="alc_todo")
        seleccion_alcaldias: list[str] = []
        if alc_todo:
            seleccion_alcaldias = alc_all
            st.caption(f"Todas seleccionadas ({len(alc_all)})")
        else:
            # casillas por alcaldía (son pocas: ~16)
            for a in alc_all:
                if st.checkbox(a, value=False, key=f"alc_{a}"):
                    seleccion_alcaldias.append(a)
            if not seleccion_alcaldias:
                st.warning("Elige al menos una alcaldía (o marca “todas”).")

    # acotar colonias a alcaldías elegidas
    # Importante: SAR/piezo a menudo vienen sin alcaldía o con nombres que no coinciden
    # con el catálogo → filtrar por igualdad de string dejaba el KPI en 0 y el mapa vacío.
    if seleccion_alcaldias:
        col_cat = col_cat[col_cat["alcaldia"].isin(seleccion_alcaldias)]
        if len(pie):
            needs_alc = (
                "alcaldia" not in pie.columns
                or pie["alcaldia"].isna().all()
                or (pie["alcaldia"].astype(str).str.strip().isin(["", "nan", "None"])).all()
            )
            if needs_alc:
                pie = assign_alcaldia_to_points(pie, colonias)
            pie = filter_points_by_alcaldias(pie, colonias, seleccion_alcaldias)
        if len(rep):
            rep = filter_points_by_alcaldias(rep, colonias, seleccion_alcaldias)
        if len(sar_map):
            sar_map = filter_points_by_alcaldias(sar_map, colonias, seleccion_alcaldias)
        if "alcaldia" in salud_map.columns and len(salud_map):
            salud_map = salud_map[salud_map["alcaldia"].isin(seleccion_alcaldias)]

    with c_col:
        st.markdown("#### Colonias")
        col_labels = sorted(col_cat["label"].dropna().unique().tolist()) if len(col_cat) else []
        col_todo = st.checkbox(
            "Seleccionar todas las colonias",
            value=True,
            key="col_todo",
            help="Si desmarcas, aparecen casillas/lista para elegir una o varias.",
        )
        seleccion_colonias: list[str] = []
        if col_todo:
            seleccion_colonias = col_labels
            st.caption(f"Todas las colonias del filtro ({len(col_labels)})")
        else:
            # Si hay demasiadas, pedimos acotar por alcaldía; si ya está acotado, casillas en scroll
            if len(seleccion_alcaldias) != 1 and len(col_labels) > 120:
                st.info(
                    "Hay muchas colonias. Elige **una sola alcaldía** a la izquierda "
                    "para ver casillas manejables, o usa la búsqueda de abajo."
                )
                seleccion_colonias = st.multiselect(
                    "Buscar y marcar colonias",
                    options=col_labels,
                    default=[],
                    placeholder="Escribe el nombre, ej. Polanco…",
                )
            else:
                # casillas en contenedor scrolleable
                busqueda = st.text_input("Filtrar lista de colonias", placeholder="Ej. Polanco, Santa Fe…")
                visibles = col_labels
                if busqueda.strip():
                    q = busqueda.strip().lower()
                    visibles = [x for x in col_labels if q in x.lower()]
                st.caption(f"Mostrando {len(visibles)} de {len(col_labels)} · marca las que quieras")
                box = st.container(height=280)
                with box:
                    for lab in visibles:
                        if st.checkbox(lab, value=False, key=f"col_{lab}"):
                            seleccion_colonias.append(lab)
            if not seleccion_colonias:
                st.warning("Elige al menos una colonia (o marca “todas”).")

    # aplicar filtro de colonias (si no es "todas" del catálogo completo del ámbito+alcaldía)
    colonia_sel_rows = col_cat.copy()
    filtro_colonias_activo = (not col_todo) and bool(seleccion_colonias)
    if filtro_colonias_activo:
        colonia_sel_rows = col_cat[col_cat["label"].isin(seleccion_colonias)]
        if "label" in pie.columns:
            pie = pie[pie["label"].isin(seleccion_colonias)]
        if "label" in rep.columns:
            rep = rep[rep["label"].isin(seleccion_colonias)]
        st.info(
            f"**Filtro activo:** {len(seleccion_alcaldias)} alcaldía(s) · {len(seleccion_colonias)} colonia(s). "
            f"Pozos: {len(pie)} · Concesiones: {rep['titulo'].nunique() if 'titulo' in rep.columns and len(rep) else len(rep)}"
        )

    # ---- KPIs (sobre filtro actual de puntos; déficit de acuíferos sigue siendo CDMX) ----
    deficit = float(oferta["deficit_hm3"].sum()) if len(oferta) and "deficit_hm3" in oferta.columns else 0.0
    if len(titles):
        tfilt = titles.copy()
        if ambito == "Corredor Poniente" and "en_poniente" in tfilt.columns:
            tfilt = tfilt[tfilt["en_poniente"] == True]  # noqa: E712
        if seleccion_alcaldias and "alcaldia" in tfilt.columns:
            tfilt = tfilt[tfilt["alcaldia"].isin(seleccion_alcaldias)]
        if filtro_colonias_activo and "label" in tfilt.columns:
            tfilt = tfilt[tfilt["label"].isin(seleccion_colonias)]
        elif filtro_colonias_activo and "colonia" in tfilt.columns:
            nombres = colonia_sel_rows["colonia"].unique().tolist()
            tfilt = tfilt[tfilt["colonia"].isin(nombres)]
        repda_hm3 = float(tfilt["volumen_hm3_anio"].sum()) if "volumen_hm3_anio" in tfilt.columns else 0.0
        n_titles = len(tfilt)
    else:
        repda_hm3, n_titles = 0.0, 0
    piezo_critico = int(pie["nivel_estres"].eq("ALTO").sum()) if len(pie) and "nivel_estres" in pie.columns else 0
    sar_count = int(len(sar_map)) if len(sar_map) else 0
    score_max = float(salud_map["score_severidad_fuga"].max()) if len(salud_map) and "score_severidad_fuga" in salud_map.columns else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Déficit acuíferos (CDMX)", f"{deficit:,.0f} hm³/año", help="Suma de déficit de acuíferos que tocan la ciudad.")
    c2.metric("Agua concesionada (filtro)", f"{repda_hm3:,.1f} hm³/año", help="Según el filtro actual (ámbito/alcaldía/colonia).")
    c3.metric("Pozos críticos (filtro)", f"{piezo_critico}")
    c4.metric("Títulos REPDA (filtro)", f"{n_titles}")
    c5.metric(
        "Puntos SAR / humedad",
        f"{sar_count}",
        help="Círculos morados en el mapa. Si ves 0 con filtro de alcaldía, suele ser desajuste de nombres; el mapa usa también ubicación geográfica.",
    )
    if piezo_critico:
        st.caption(
            f"Hay **{piezo_critico} pozos críticos (ALTO)** en el filtro: "
            "abajo en Torre de control aparece la tabla con alcaldía y recomendación más cercana."
        )
    if score_max > 0:
        st.caption(f"Score máximo de severidad de fuga (filtro): **{score_max:.0f}/100**")

    st.divider()

    # ---- Controles del mapa (torre de control) ----
    st.markdown(
        """
        <div style="background:linear-gradient(160deg,#070b14 0%,#0f1a2e 55%,#132238 100%);
        border:1px solid #1e3a5f;border-radius:14px;padding:16px 18px 6px 18px;margin:4px 0 10px 0;
        box-shadow:inset 0 1px 0 rgba(125,190,255,0.12);">
          <div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <div>
              <div style="font-size:0.72rem;letter-spacing:0.14em;text-transform:uppercase;color:#5b9ec9;">
                ZASEVA · Sala de situación
              </div>
              <div style="font-size:1.15rem;font-weight:650;color:#e8f1fa;margin-top:2px;">
                Torre de control territorial
              </div>
            </div>
            <div style="font-size:0.78rem;color:#8aa4bd;">
              Capas · Foco · Atención prioritaria
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ctrl1, ctrl2 = st.columns([1.35, 1])
    with ctrl1:
        st.markdown("**Capas operativas**")
        c_sar, c_piezo, c_repda, c_poly = st.columns(4)
        with c_sar:
            mostrar_sar = st.checkbox(
                "Humedad SAR",
                value=True,
                key="show_sar",
                help="Círculos morados: humedad anómala Sentinel-1 (alerta de inspección).",
            )
        with c_piezo:
            mostrar_piezo = st.checkbox("Pozos / estrés", value=True, key="show_piezo")
        with c_repda:
            mostrar_repda = st.checkbox(
                "REPDA",
                value=False,
                key="show_repda",
                help="Derecho legal de extracción (presión formal). No es bombeo en vivo.",
            )
        with c_poly:
            mostrar_poly = st.checkbox("Polígonos", value=False, key="show_poly")

    with ctrl2:
        alc_mapa_opts = sorted(col_cat["alcaldia"].dropna().unique().tolist()) if len(col_cat) else sorted(seleccion_alcaldias)
        if not alc_mapa_opts and seleccion_alcaldias:
            alc_mapa_opts = sorted(seleccion_alcaldias)
        alcaldias_mapa = st.multiselect(
            "Foco alcaldía / municipio",
            options=alc_mapa_opts,
            default=seleccion_alcaldias if seleccion_alcaldias else alc_mapa_opts,
            help="Deja una sola alcaldía para la reunión con esa gobernación.",
        )
        if not alcaldias_mapa and alc_mapa_opts:
            alcaldias_mapa = alc_mapa_opts

    # Asignar alcaldía a pozos si viene vacía (Supabase)
    if len(pie) and (pie.get("alcaldia", pd.Series(dtype=str)).astype(str).str.len().fillna(0) == 0).all():
        pie = assign_alcaldia_to_points(pie, colonias)

    pie_mapa = filter_points_by_alcaldias(pie.copy(), colonias, alcaldias_mapa)
    rep_mapa = filter_points_by_alcaldias(rep.copy(), colonias, alcaldias_mapa)
    sar_vista = filter_points_by_alcaldias(sar_map.copy(), colonias, alcaldias_mapa)
    # Nunca dejar la capa SAR en 0 si la BD sí trajo puntos (filtros agresivos / nombres)
    if sar_vista.empty and len(sar_map):
        sar_vista = sar_map.copy()
    if sar_vista.empty and len(sar_bruto):
        sar_vista = sar_bruto.copy()
        st.info(
            "El filtro de alcaldía dejó 0 humedades; mostrando **todos** los puntos SAR cargados "
            "(el ETL actual cubre sobre todo el **Corredor Poniente**, no las 16 alcaldías)."
        )

    # Recalcular KPI SAR con el foco real del mapa
    sar_count = int(len(sar_vista))
    piezo_critico = int(pie_mapa["nivel_estres"].astype(str).str.upper().eq("ALTO").sum()) if len(pie_mapa) and "nivel_estres" in pie_mapa.columns else 0

    st.markdown(
        f"""
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 12px 0;">
          <div style="background:#1a2332;border:1px solid #334155;border-radius:10px;padding:8px 12px;color:#e2e8f0;">
            <span style="color:#94a3b8;font-size:0.75rem;">FOCO</span><br/>
            <b>{', '.join(alcaldias_mapa) if alcaldias_mapa else 'Todas'}</b>
          </div>
          <div style="background:#1a2332;border:1px solid #7c3aed;border-radius:10px;padding:8px 12px;color:#e2e8f0;">
            <span style="color:#c4b5fd;font-size:0.75rem;">HUMEDAD (MORADO)</span><br/>
            <b>{len(sar_vista)}</b> señales
            <span style="color:#94a3b8;font-size:0.7rem;"> · bruto {len(sar_bruto)}</span>
          </div>
          <div style="background:#1a2332;border:1px solid #ef4444;border-radius:10px;padding:8px 12px;color:#e2e8f0;">
            <span style="color:#fca5a5;font-size:0.75rem;">POZOS CRÍTICOS</span><br/>
            <b>{piezo_critico}</b> ALTO
          </div>
          <div style="background:#1a2332;border:1px solid #64748b;border-radius:10px;padding:8px 12px;color:#e2e8f0;">
            <span style="color:#94a3b8;font-size:0.75rem;">REPDA</span><br/>
            <b>{len(rep_mapa)}</b> puntos
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Selector pozo ----
    if "pozo_sel" not in st.session_state:
        st.session_state.pozo_sel = None

    pie_series = pie_mapa[pie_mapa["n_obs"] >= 2] if "n_obs" in pie_mapa.columns else pie_mapa
    pie_series = (
        pie_series[pie_series["tasa_abatimiento_m_anio"].notna()]
        if "tasa_abatimiento_m_anio" in pie_series.columns
        else pie_series
    )
    criticos_pool = (
        pie_series[pie_series["nivel_estres"].astype(str).str.upper() == "ALTO"].copy()
        if len(pie_series) and "nivel_estres" in pie_series.columns
        else pie_series.head(0)
    )

    pozo_opts = ["(Ver mapa del filtro actual)"] + [
        f"{int(r.num_pozo)} · {r.semaforo} · {getattr(r, 'colonia', '')}"
        for r in pie_series.sort_values("tasa_abatimiento_m_anio", ascending=False).itertuples()
        if pd.notna(getattr(r, "num_pozo", None))
    ]
    sel = st.selectbox("🔎 Enfocar un pozo de medición", pozo_opts)
    if sel and sel != "(Ver mapa del filtro actual)":
        st.session_state.pozo_sel = int(sel.split("·")[0].strip())

    # Tabla operativa de pozos críticos (siempre visible para atención)
    crit_tabla = enrich_critical_wells(pie_mapa if len(pie_mapa) else pie)
    if len(crit_tabla):
        st.markdown("#### Pozos críticos (abatimiento ALTO) — atención prioritaria")
        st.caption("Lista accionable para gobernación: dónde duele + alternativa preferible más cercana.")
        crit_view = crit_tabla[
            [c for c in [
                "num_pozo", "colonia", "alcaldia", "tasa_abatimiento_m_anio",
                "semaforo", "recomendacion_cercana", "dist_recomendacion_km", "latitud", "longitud",
            ] if c in crit_tabla.columns]
        ].rename(columns={
            "num_pozo": "No. pozo",
            "colonia": "Colonia",
            "alcaldia": "Alcaldía",
            "tasa_abatimiento_m_anio": "Bajada (m/año)",
            "semaforo": "Semáforo",
            "recomendacion_cercana": "Recomendación más cercana",
            "dist_recomendacion_km": "Dist. km",
            "latitud": "Lat",
            "longitud": "Lon",
        })
        st.dataframe(crit_view, use_container_width=True, hide_index=True, height=260)

    left, right = st.columns([1.65, 1], gap="large")

    with left:
        st.markdown("### Mapa")
        st.caption(
            "**Morado = humedad anómala (alerta de inspección).** "
            "Hoy el satélite está cargado sobre el **Corredor Poniente** (oeste), no sobre las 16 alcaldías. "
            "Al pasar el mouse sobre humedad o pozo crítico verás los **3 pozos ALTO más cercanos**."
        )
        with st.expander("Leyenda (plática con alcaldías)", expanded=False):
            st.markdown(
                """
                | Color | Significa |
                |---|---|
                | **Morado** | Humedad anómala Sentinel-1 (alerta de inspección, no fuga confirmada) |
                | **Rojo** | Pozo abatimiento ALTO |
                | **Naranja** | Pozo MEDIO |
                | **Verde / teal** | Pozo leve o estable |
                | **Anillo** | Concesión REPDA (derecho legal de extracción) |
                """
            )

        layers = []
        if (
            mostrar_poly
            and filtro_colonias_activo
            and len(colonias_geo)
            and len(seleccion_colonias)
        ):
            labs = seleccion_colonias[:40]
            poly = colonias_geo[colonias_geo["label"].isin(labs)]
            if alcaldias_mapa and "alcaldia" in getattr(poly, "columns", []):
                poly = poly[poly["alcaldia"].isin(alcaldias_mapa)]
            if len(poly):
                layers.append(
                    pdk.Layer(
                        "GeoJsonLayer",
                        data=poly.__geo_interface__,
                        stroked=True,
                        filled=True,
                        get_fill_color="[140, 80, 200, 40]",
                        get_line_color="[200, 160, 255, 210]",
                        line_width_min_pixels=2,
                    )
                )

        pmap = pie_series.copy() if len(pie_series) else pie_mapa.copy()
        color_map = {
            "ALTO": [255, 90, 70, 230],
            "MEDIO": [255, 180, 60, 210],
            "LEVE": [80, 200, 120, 200],
            "RECUPERACION_O_ESTABLE": [40, 200, 190, 200],
        }
        if mostrar_piezo and len(pmap):
            pmap = pmap.copy()
            pmap["fill_color"] = pmap["nivel_estres"].map(
                lambda x: color_map.get(str(x).upper(), [160, 160, 160, 180])
            )
            pmap["radius"] = 90
            if st.session_state.pozo_sel is not None:
                pmap.loc[pmap["num_pozo"] == st.session_state.pozo_sel, "radius"] = 220
            # En pozos críticos: 3 ALTO más cercanos
            tip_near = []
            for r in pmap.itertuples():
                if str(getattr(r, "nivel_estres", "")).upper() == "ALTO":
                    tip_near.append(nearest_points_text(r.latitud, r.longitud, criticos_pool, n=3))
                else:
                    tip_near.append("")
            pmap["tip_titulo"] = pmap["num_pozo"].map(lambda x: f"Pozo {int(x)}" if pd.notna(x) else "Pozo")
            pmap["tip_linea1"] = (
                pmap.get("alcaldia", pd.Series([""] * len(pmap))).fillna("").astype(str)
                + " · "
                + pmap.get("colonia", pd.Series([""] * len(pmap))).fillna("").astype(str)
            )
            pmap["tip_linea2"] = pmap.get("semaforo", pd.Series([""] * len(pmap))).fillna("").astype(str)
            consejos = (
                pmap["consejo_para_piperos"].fillna("").astype(str).tolist()
                if "consejo_para_piperos" in pmap.columns
                else [""] * len(pmap)
            )
            pmap["tip_linea3"] = [
                f"3 críticos cercanos: {t}" if t else consejos[i]
                for i, t in enumerate(tip_near)
            ]
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=pmap,
                    id="piezo",
                    get_position="[longitud, latitud]",
                    get_radius="radius",
                    get_fill_color="fill_color",
                    pickable=True,
                    auto_highlight=True,
                )
            )

        if mostrar_repda and len(rep_mapa) and {"latitud", "longitud"}.issubset(rep_mapa.columns):
            rmap = rep_mapa.dropna(subset=["latitud", "longitud"]).copy()
            vol_col = "volumen_punto_m3_anio" if "volumen_punto_m3_anio" in rmap.columns else "volumen_m3_anio"
            vmax = max(float(rmap[vol_col].max()), 1.0) if vol_col in rmap.columns and len(rmap) else 1.0
            rmap["radius"] = 30 + 140 * (rmap[vol_col] / vmax) ** 0.5 if vol_col in rmap.columns else 45
            rmap["tip_titulo"] = "Concesión REPDA"
            rmap["tip_linea1"] = rmap.get("titular", pd.Series([""] * len(rmap))).fillna("").astype(str)
            rmap["tip_linea2"] = rmap.get("uso", pd.Series([""] * len(rmap))).fillna("").astype(str)
            rmap["tip_linea3"] = (
                rmap[vol_col].map(lambda v: f"Volumen autorizado: {v:,.0f} m³/año")
                if vol_col in rmap.columns
                else ""
            )
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=rmap,
                    id="repda",
                    get_position="[longitud, latitud]",
                    get_radius="radius",
                    stroked=True,
                    filled=False,
                    get_line_color="[200, 210, 220, 200]",
                    line_width_min_pixels=1,
                    pickable=True,
                )
            )

        if mostrar_sar and len(sar_vista) and {"latitud", "longitud"}.issubset(sar_vista.columns):
            smap = sar_vista.dropna(subset=["latitud", "longitud"]).copy()
            # Si tras filtros queda vacío, mostrar SAR del ámbito sin filtro de nombre
            if smap.empty and len(sar_map):
                smap = sar_map.dropna(subset=["latitud", "longitud"]).copy()
            smap["radius"] = 180
            smap["tip_titulo"] = "Humedad anómala (alerta de inspección)"
            smap["tip_linea1"] = smap.apply(
                lambda r: f"{r.get('alcaldia', '')} · {r.get('fecha_escena', '')}".strip(" ·"),
                axis=1,
            )
            smap["tip_linea2"] = smap.apply(
                lambda r: (
                    f"Backscatter {float(r['backscatter_db']):.1f} dB · Δ {float(r['delta_db']):.1f} dB"
                    if pd.notna(r.get("backscatter_db")) and pd.notna(r.get("delta_db"))
                    else "Señal dieléctrica anómala"
                ),
                axis=1,
            )
            smap["tip_linea3"] = smap.apply(
                lambda r: "3 pozos críticos cercanos: " + nearest_points_text(
                    float(r["latitud"]), float(r["longitud"]), criticos_pool, n=3
                ),
                axis=1,
            )
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=smap,
                    id="sar",
                    get_position="[longitud, latitud]",
                    get_radius="radius",
                    radius_min_pixels=6,
                    radius_max_pixels=28,
                    get_fill_color="[168, 85, 247, 220]",  # morado
                    get_line_color="[233, 213, 255, 255]",
                    line_width_min_pixels=1,
                    stroked=True,
                    filled=True,
                    pickable=True,
                )
            )
        elif mostrar_sar:
            st.info(
                "Capa de humedad activada, pero no hay puntos en este foco. "
                "Prueba “Corredor Poniente” o quita filtros de alcaldía estrechos."
            )

        if st.session_state.pozo_sel is not None and len(pmap) and (pmap["num_pozo"] == st.session_state.pozo_sel).any():
            row = pmap[pmap["num_pozo"] == st.session_state.pozo_sel].iloc[0]
            view = pdk.ViewState(latitude=float(row.latitud), longitude=float(row.longitud), zoom=13.5)
        elif mostrar_sar and len(sar_vista) and {"latitud", "longitud"}.issubset(sar_vista.columns):
            # Centrar en el parche Sentinel-1 (hoy: Corredor Poniente)
            view = pdk.ViewState(
                latitude=float(sar_vista["latitud"].mean()),
                longitude=float(sar_vista["longitud"].mean()),
                zoom=11.4,
            )
        elif filtro_colonias_activo and len(colonia_sel_rows):
            view = pdk.ViewState(
                latitude=float(colonia_sel_rows["latitud_centro"].mean()),
                longitude=float(colonia_sel_rows["longitud_centro"].mean()),
                zoom=12.5 if len(seleccion_colonias) <= 3 else 11.5,
            )
        elif alcaldias_mapa and len(col_cat):
            foc = col_cat[col_cat["alcaldia"].isin(alcaldias_mapa)] if "alcaldia" in col_cat.columns else col_cat
            if len(foc) and {"latitud_centro", "longitud_centro"}.issubset(foc.columns):
                view = pdk.ViewState(
                    latitude=float(foc["latitud_centro"].mean()),
                    longitude=float(foc["longitud_centro"].mean()),
                    zoom=11.2 if len(alcaldias_mapa) <= 2 else 10.4,
                )
            else:
                view = pdk.ViewState(latitude=19.36, longitude=-99.15, zoom=10.2)
        elif ambito == "Corredor Poniente":
            view = pdk.ViewState(latitude=19.35, longitude=-99.28, zoom=11)
        else:
            view = pdk.ViewState(latitude=19.36, longitude=-99.15, zoom=10.2)

        event = st.pydeck_chart(
            pdk.Deck(
                layers=layers,
                initial_view_state=view,
                map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
                tooltip={
                    "html": "<b>{tip_titulo}</b><br/>{tip_linea1}<br/>{tip_linea2}<br/>{tip_linea3}",
                    "style": {"backgroundColor": "#0b1220", "color": "#f3e8ff"},
                },
            ),
            use_container_width=True,
            height=560,
            on_select="rerun",
            selection_mode="single-object",
            key="mapa_cdmx",
        )
        try:
            objects = event.selection.get("objects", {}) if event and event.selection else {}
            hits = objects.get("piezo") or []
            if hits and "num_pozo" in hits[0]:
                st.session_state.pozo_sel = int(hits[0]["num_pozo"])
        except Exception:
            pass

        if st.session_state.pozo_sel is not None and len(pmap):
            det = pmap[pmap["num_pozo"] == st.session_state.pozo_sel]
            if len(det):
                d = det.iloc[0]
                st.success(
                    f"**Pozo {int(d['num_pozo'])}** · {d.get('colonia', '')} ({d.get('alcaldia', '')}) · "
                    f"{d['semaforo']} · Bajada: **{d['tasa_abatimiento_m_anio']:.2f} m/año** · {d['consejo_para_piperos']}"
                )

    with right:
        st.markdown("### Humedad anómala por alcaldía")
        st.caption(
            "Conteo de señales SAR (fugas invisibles proxy). "
            "Úsalo para priorizar: más puntos = más urgente revisar la red."
        )

        hum = humedad_por_alcaldia(
            sar=sar_vista if len(sar_vista) else sar_map,
            salud=salud_map if len(salud_map) else salud,
            diagnostico=diagnostico,
            colonias=colonias,
            alcaldias_filtro=alcaldias_mapa if alcaldias_mapa else (seleccion_alcaldias if seleccion_alcaldias else None),
        )
        if len(hum):
            top = hum.iloc[0]
            st.warning(
                f"**Prioridad sugerida:** {top['alcaldia']} — "
                f"**{int(top['humedades_anomalas'])}** señales de humedad anómala. "
                f"{top.get('prioridad', '')}"
            )
            hum_view = hum.rename(
                columns={
                    "alcaldia": "Alcaldía / municipio",
                    "humedades_anomalas": "No. humedades anómalas",
                    "score_severidad_max": "Score máx. severidad",
                    "nivel_riesgo_estructural": "Riesgo",
                    "prioridad": "Prioridad de revisión",
                }
            )
            st.dataframe(hum_view, use_container_width=True, hide_index=True, height=280)
            st.markdown(
                """
                **Frase lista para alcaldía:**  
                *“Detectamos N señales de humedad anómala en su territorio. 
                No es lluvia ni sequía del semáforo oficial: es posible pérdida de agua en red. 
                ZASEVA ayuda a localizar, priorizar y coordinar la logística de solución.”*
                """.replace("N", str(int(hum["humedades_anomalas"].sum())))
            )
            if "No. humedades anómalas" in hum_view.columns:
                chart_df = hum_view.head(8).copy()
                st.bar_chart(
                    chart_df,
                    x="Alcaldía / municipio",
                    y="No. humedades anómalas",
                    horizontal=True,
                )
        else:
            st.info(
                "Aún no hay conteo de humedad anómala por alcaldía. "
                "Verifica que el ETL SAR haya corrido y que Supabase tenga filas."
            )

        with st.expander("Acuíferos que tocan CDMX", expanded=False):
            oferta_view = pd.DataFrame(
                {
                    "Clave acuífero": oferta.get("cve_acui"),
                    "Nombre del acuífero": oferta.get("nom_acui"),
                    "Entidad": oferta.get("nom_edo"),
                    "Recarga (hm³/año)": oferta.get("recarga_to_hm3"),
                    "Déficit (hm³/año)": oferta.get("deficit_hm3"),
                }
            )
            st.dataframe(oferta_view, use_container_width=True, hide_index=True)

        with st.expander("Sequía oficial por alcaldía (contexto)", expanded=False):
            st.caption(
                "Útil como contraste: a veces el semáforo dice “sin sequía” y aun así hay déficit "
                "estructural + humedad anómala (pérdidas de red)."
            )
            if len(sequia):
                sequia_view = pd.DataFrame(
                    {
                        "Alcaldía / municipio": sequia.get("nombre_mun"),
                        "Semáforo sequía": sequia.get("sps"),
                        "Reducción pedida": sequia.get("ahorro_uso_eficiente"),
                    }
                )
                st.dataframe(sequia_view, use_container_width=True, hide_index=True, height=220)
            else:
                st.info("Sin datos de sequía.")

        with st.expander("Concesiones por uso (filtro actual)", expanded=False):
            if len(titles):
                tfilt = titles.copy()
                if ambito == "Corredor Poniente" and "en_poniente" in tfilt.columns:
                    tfilt = tfilt[tfilt["en_poniente"] == True]  # noqa: E712
                if seleccion_alcaldias and "alcaldia" in tfilt.columns:
                    tfilt = tfilt[tfilt["alcaldia"].isin(seleccion_alcaldias)]
                if filtro_colonias_activo and "colonia" in tfilt.columns:
                    tfilt = tfilt[tfilt["colonia"].isin(colonia_sel_rows["colonia"].unique())]
                if len(tfilt):
                    uso = (
                        tfilt.groupby("uso", dropna=False)["volumen_hm3_anio"]
                        .sum()
                        .sort_values(ascending=False)
                        .reset_index()
                        .rename(columns={"uso": "Uso del agua", "volumen_hm3_anio": "hm³ / año"})
                    )
                    st.bar_chart(uso, x="Uso del agua", y="hm³ / año", horizontal=True)
                else:
                    st.write("Sin títulos en este filtro.")
            else:
                st.write("Sin títulos.")

    st.divider()
    st.markdown("### Diagnóstico B2G — alcaldías (Sentinel-1 × acuífero × pozos)")
    st.caption(
        "Vista para plática con municipios: fugas invisibles, déficit del acuífero y riesgo estructural de red. "
        "Se alimenta de `vista_diagnostico_alcaldia_resumen` en Supabase."
    )
    if len(diagnostico):
        diag_view = diagnostico.rename(
            columns={
                "alcaldia": "Alcaldía",
                "puntos_criticos_fugas": "Puntos críticos fugas",
                "deficit_acuifero_hm3_promedio": "Déficit acuífero (hm³)",
                "score_severidad_promedio": "Score promedio",
                "score_severidad_max": "Score máximo",
                "nivel_riesgo_estructural": "Riesgo estructural",
                "n_colonias": "Colonias",
            }
        )
        st.dataframe(diag_view, use_container_width=True, hide_index=True)
    elif db_ok:
        st.info(
            "Supabase está configurado, pero aún no hay filas en el diagnóstico SAR. "
            "Corre el ETL satelital y recarga la app."
        )
    else:
        st.info(
            "Para ver este bloque: configura `SUPABASE_DB_URL` en Streamlit Secrets "
            "y asegúrate de haber corrido el ETL SAR."
        )

    if len(salud):
        with st.expander("Detalle de celdas con mayor score de severidad", expanded=False):
            top = salud.head(25).rename(
                columns={
                    "colonia": "Colonia",
                    "alcaldia": "Alcaldía",
                    "score_severidad_fuga": "Score fuga",
                    "nivel_riesgo_red": "Riesgo",
                    "score_sar_humedad": "Score SAR",
                    "score_abatimiento": "Score abatimiento",
                    "deficit_acui_hm3": "Déficit hm³",
                    "fecha_calculo": "Fecha",
                }
            )
            st.dataframe(top, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### Para piperos — guía del filtro actual")
    st.caption("Proxy de estrés del nivel freático (no es medidor de tanque lleno en vivo).")

    preferir = pie_series[pie_series["nivel_estres"].isin(["RECUPERACION_O_ESTABLE", "LEVE"])].sort_values(
        "tasa_abatimiento_m_anio"
    ) if len(pie_series) else pie.head(0)
    evitar = pie_series[pie_series["nivel_estres"] == "ALTO"].sort_values(
        "tasa_abatimiento_m_anio", ascending=False
    ) if len(pie_series) else pie.head(0)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### ✅ Más preferibles")
        if len(preferir):
            st.dataframe(
                piezo_table_view(preferir.head(8)),
                use_container_width=True,
                hide_index=True,
            )
            best = preferir.iloc[0]
            if st.button(f"Enfocar pozo {int(best['num_pozo'])}", key="btn_best"):
                st.session_state.pozo_sel = int(best["num_pozo"])
                st.rerun()
        else:
            st.write("No hay pozos ‘preferibles’ en este filtro.")

    with col_b:
        st.markdown("#### ⛔ Más críticos")
        if len(evitar):
            st.dataframe(
                piezo_table_view(evitar.head(8)),
                use_container_width=True,
                hide_index=True,
            )
            worst = evitar.iloc[0]
            if st.button(f"Enfocar pozo {int(worst['num_pozo'])}", key="btn_worst"):
                st.session_state.pozo_sel = int(worst["num_pozo"])
                st.rerun()
        else:
            st.write("No hay pozos críticos en este filtro.")

    st.divider()
    t1, t2 = st.tabs(["Pozos del filtro", "Títulos REPDA del filtro"])
    with t1:
        if len(pie_series):
            full = pie_series.sort_values("tasa_abatimiento_m_anio", ascending=False)
            full_view = piezo_table_view(full, include_coords=True)
            selected = st.dataframe(
                full_view,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="tabla_pozos_cdmx",
            )
            try:
                rows = selected.selection.rows if selected and selected.selection else []
                if rows:
                    st.session_state.pozo_sel = int(full.iloc[rows[0]]["num_pozo"])
            except Exception:
                pass
        else:
            st.write("Sin pozos para este filtro.")

    with t2:
        if len(titles):
            tfilt = titles.copy()
            if ambito == "Corredor Poniente" and "en_poniente" in tfilt.columns:
                tfilt = tfilt[tfilt["en_poniente"] == True]  # noqa: E712
            if seleccion_alcaldias and "alcaldia" in tfilt.columns:
                tfilt = tfilt[tfilt["alcaldia"].isin(seleccion_alcaldias)]
            if filtro_colonias_activo and "colonia" in tfilt.columns:
                tfilt = tfilt[tfilt["colonia"].isin(colonia_sel_rows["colonia"].unique())]
            top = tfilt.sort_values("volumen_m3_anio", ascending=False).head(15)
            st.dataframe(
                pd.DataFrame(
                    {
                        "Título": top.get("titulo"),
                        "Colonia": top.get("colonia"),
                        "Alcaldía": top.get("alcaldia"),
                        "Uso": top.get("uso"),
                        "Volumen autorizado (m³/año)": top.get("volumen_m3_anio"),
                        "Titular": top.get("titular"),
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("Sin títulos para este filtro.")

    with st.expander("Notas y límites de esta versión"):
        st.markdown(
            """
            - **CDMX completa** en catálogo de colonias y concesiones/puntos disponibles.
            - El semáforo de pozo es un **proxy** (bajada del nivel), no litros disponibles hoy.
            - La capa **SAR** es un proxy de humedad anómala (Sentinel-1), no una fuga confirmada en campo.
            - Si una colonia no tiene pozo de medición cerca, verás pocas filas: usa alcaldía o Toda CDMX.
            - Huixquilucan (Edomex) no está en “Toda la CDMX”; el foco poniente CDMX cubre Cuajimalpa/AO/Miguel Hidalgo/Magdalena Contreras.
            - Streamlit Cloud necesita el secret `SUPABASE_DB_URL` para leer SAR y el diagnóstico B2G.
            """
        )


if __name__ == "__main__":
    main()
