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
    try:
        url = st.secrets.get("SUPABASE_DB_URL")  # type: ignore[attr-defined]
        if url:
            return str(url).strip()
    except Exception:
        pass
    url = os.environ.get("SUPABASE_DB_URL")
    return url.strip() if url else None


@st.cache_data(ttl=300)
def load_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_data(ttl=300)
def load_sql(query: str) -> pd.DataFrame:
    """Lee una consulta SQL desde Supabase. Vacío si no hay URL o falla."""
    url = get_db_url()
    if not url:
        return pd.DataFrame()
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url)
        with engine.connect() as conn:
            return pd.read_sql(text(query), conn)
    except Exception:
        return pd.DataFrame()


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
    out["num_pozo"] = out["num_pozo"].astype(int)
    if "en_poniente" in out.columns:
        out["en_poniente"] = out["en_poniente"].astype(str).str.lower().isin(["true", "1", "yes"])
    return out


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

    sar = load_sql(
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
    diagnostico = layers["diagnostico"]
    salud = layers["salud"]
    fuente = layers["fuente"]
    db_ok = layers["db_ok"]

    if db_ok:
        st.caption(f"Fuente de datos: **{fuente}** · Supabase conectado.")
    else:
        st.caption(
            "Fuente de datos: **CSV local**. "
            "Para activar satélite/diagnóstico: configura `SUPABASE_DB_URL` en Streamlit Secrets."
        )

    colonias = load_csv("colonias_cdmx.csv")
    colonias_geo = load_colonias_geo()

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
    if ambito == "Corredor Poniente":
        if "en_poniente" in col_cat.columns:
            col_cat = col_cat[col_cat["en_poniente"] == True]  # noqa: E712
        if "en_poniente" in pie.columns:
            pie = pie[pie["en_poniente"] == True]  # noqa: E712
        if "en_poniente" in rep.columns:
            rep = rep[rep["en_poniente"] == True]  # noqa: E712
        elif "en_bbox_piloto" in pie.columns:
            pie = pie[pie["en_bbox_piloto"] == True]  # noqa: E712

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
    if seleccion_alcaldias:
        col_cat = col_cat[col_cat["alcaldia"].isin(seleccion_alcaldias)]
        if "alcaldia" in pie.columns:
            pie = pie[pie["alcaldia"].isin(seleccion_alcaldias)]
        if "alcaldia" in rep.columns:
            rep = rep[rep["alcaldia"].isin(seleccion_alcaldias)]

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
    sar_count = int(len(sar)) if len(sar) else 0
    score_max = float(salud["score_severidad_fuga"].max()) if len(salud) and "score_severidad_fuga" in salud.columns else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Déficit acuíferos (CDMX)", f"{deficit:,.0f} hm³/año", help="Suma de déficit de acuíferos que tocan la ciudad.")
    c2.metric("Agua concesionada (filtro)", f"{repda_hm3:,.1f} hm³/año", help="Según el filtro actual (ámbito/alcaldía/colonia).")
    c3.metric("Pozos críticos (filtro)", f"{piezo_critico}")
    c4.metric("Títulos REPDA (filtro)", f"{n_titles}")
    c5.metric(
        "Puntos SAR / humedad",
        f"{sar_count}",
        help="Anomalías Sentinel-1 (humedad anómala) cargadas desde Supabase.",
    )
    if score_max > 0:
        st.caption(f"Score máximo de severidad de fuga en mapa salud: **{score_max:.0f}/100**")

    st.divider()

    # ---- Selector pozo ----
    if "pozo_sel" not in st.session_state:
        st.session_state.pozo_sel = None

    pie_series = pie[pie["n_obs"] >= 2] if "n_obs" in pie.columns else pie
    pie_series = pie_series[pie_series["tasa_abatimiento_m_anio"].notna()] if "tasa_abatimiento_m_anio" in pie_series.columns else pie_series
    pozo_opts = ["(Ver mapa del filtro actual)"] + [
        f"{int(r.num_pozo)} · {r.semaforo} · {getattr(r, 'colonia', '')}"
        for r in pie_series.sort_values("tasa_abatimiento_m_anio", ascending=False).itertuples()
    ]
    sel = st.selectbox("🔎 Enfocar un pozo de medición", pozo_opts)
    if sel and sel != "(Ver mapa del filtro actual)":
        st.session_state.pozo_sel = int(sel.split("·")[0].strip())

    left, right = st.columns([1.65, 1], gap="large")

    with left:
        st.markdown("### Mapa")
        st.caption(
            "Color = estrés del nivel freático. Anillos = concesiones REPDA. "
            "Puntos cyan = humedad anómala Sentinel-1. El polígono aparece si marcas colonias específicas."
        )

        layers = []
        mostrar_sar = st.checkbox("Mostrar anomalías SAR (fugas invisibles)", value=True, key="show_sar")
        # polígonos de colonias seleccionadas (máx 40 para no saturar)
        if filtro_colonias_activo and len(colonias_geo) and len(seleccion_colonias):
            labs = seleccion_colonias[:40]
            poly = colonias_geo[colonias_geo["label"].isin(labs)]
            if len(poly):
                layers.append(
                    pdk.Layer(
                        "GeoJsonLayer",
                        data=poly.__geo_interface__,
                        stroked=True,
                        filled=True,
                        get_fill_color="[11, 60, 77, 40]",
                        get_line_color="[11, 60, 77, 220]",
                        line_width_min_pixels=2,
                    )
                )

        pmap = pie_series.copy() if len(pie_series) else pie.copy()
        color_map = {
            "ALTO": [196, 92, 38, 210],
            "MEDIO": [212, 160, 23, 200],
            "LEVE": [61, 124, 71, 190],
            "RECUPERACION_O_ESTABLE": [31, 122, 108, 190],
        }
        if len(pmap):
            pmap["fill_color"] = pmap["nivel_estres"].map(
                lambda x: color_map.get(str(x).upper(), [120, 120, 120, 160])
            )
            pmap["radius"] = 90
            if st.session_state.pozo_sel is not None:
                pmap.loc[pmap["num_pozo"] == st.session_state.pozo_sel, "radius"] = 220
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

        if len(rep) and {"latitud", "longitud"}.issubset(rep.columns):
            rmap = rep.dropna(subset=["latitud", "longitud"]).copy()
            vol_col = "volumen_punto_m3_anio" if "volumen_punto_m3_anio" in rmap.columns else "volumen_m3_anio"
            vmax = max(float(rmap[vol_col].max()), 1.0) if vol_col in rmap.columns and len(rmap) else 1.0
            rmap["radius"] = 30 + 140 * (rmap[vol_col] / vmax) ** 0.5 if vol_col in rmap.columns else 45
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=rmap,
                    id="repda",
                    get_position="[longitud, latitud]",
                    get_radius="radius",
                    stroked=True,
                    filled=False,
                    get_line_color="[11, 60, 77, 170]",
                    line_width_min_pixels=1,
                    pickable=True,
                )
            )

        if mostrar_sar and len(sar) and {"latitud", "longitud"}.issubset(sar.columns):
            smap = sar.dropna(subset=["latitud", "longitud"]).copy()
            if ambito == "Corredor Poniente":
                smap = smap[
                    (smap["longitud"] >= -99.31)
                    & (smap["longitud"] <= -99.15)
                    & (smap["latitud"] >= 19.30)
                    & (smap["latitud"] <= 19.45)
                ]
            smap["radius"] = 55
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=smap,
                    id="sar",
                    get_position="[longitud, latitud]",
                    get_radius="radius",
                    get_fill_color="[0, 160, 180, 170]",
                    pickable=True,
                )
            )

        # view
        if st.session_state.pozo_sel is not None and len(pmap) and (pmap["num_pozo"] == st.session_state.pozo_sel).any():
            row = pmap[pmap["num_pozo"] == st.session_state.pozo_sel].iloc[0]
            view = pdk.ViewState(latitude=float(row.latitud), longitude=float(row.longitud), zoom=13.5)
        elif filtro_colonias_activo and len(colonia_sel_rows):
            view = pdk.ViewState(
                latitude=float(colonia_sel_rows["latitud_centro"].mean()),
                longitude=float(colonia_sel_rows["longitud_centro"].mean()),
                zoom=12.5 if len(seleccion_colonias) <= 3 else 11.5,
            )
        elif ambito == "Corredor Poniente":
            view = pdk.ViewState(latitude=19.35, longitude=-99.28, zoom=11)
        else:
            view = pdk.ViewState(latitude=19.36, longitude=-99.15, zoom=10.2)

        event = st.pydeck_chart(
            pdk.Deck(
                layers=layers,
                initial_view_state=view,
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                tooltip={
                    "html": "<b>Pozo {num_pozo}</b><br/>{colonia}<br/>{semaforo}<br/>{consejo_para_piperos}",
                    "style": {"backgroundColor": "#0b3c4d", "color": "white"},
                },
            ),
            use_container_width=True,
            height=540,
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
        st.markdown("### Acuíferos que tocan CDMX")
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

        st.markdown("### Sequía oficial por alcaldía")
        if len(sequia):
            sequia_view = pd.DataFrame(
                {
                    "Alcaldía / municipio": sequia.get("nombre_mun"),
                    "Semáforo sequía": sequia.get("sps"),
                    "Reducción pedida": sequia.get("ahorro_uso_eficiente"),
                }
            )
            st.dataframe(sequia_view, use_container_width=True, hide_index=True, height=260)
        else:
            st.info("Sin datos de sequía.")

        st.markdown("### Concesiones por uso (filtro actual)")
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
                preferir.head(8)[["num_pozo", "colonia", "alcaldia", "semaforo", "tasa_abatimiento_m_anio", "consejo_para_piperos"]].rename(
                    columns={
                        "num_pozo": "No. pozo",
                        "colonia": "Colonia",
                        "alcaldia": "Alcaldía",
                        "semaforo": "Semáforo",
                        "tasa_abatimiento_m_anio": "Bajada (m/año)",
                        "consejo_para_piperos": "Consejo",
                    }
                ),
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
                evitar.head(8)[["num_pozo", "colonia", "alcaldia", "semaforo", "tasa_abatimiento_m_anio", "consejo_para_piperos"]].rename(
                    columns={
                        "num_pozo": "No. pozo",
                        "colonia": "Colonia",
                        "alcaldia": "Alcaldía",
                        "semaforo": "Semáforo",
                        "tasa_abatimiento_m_anio": "Bajada (m/año)",
                        "consejo_para_piperos": "Consejo",
                    }
                ),
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
            full_view = full[
                ["num_pozo", "colonia", "alcaldia", "semaforo", "tasa_abatimiento_m_anio", "consejo_para_piperos", "latitud", "longitud"]
            ].rename(
                columns={
                    "num_pozo": "No. pozo",
                    "colonia": "Colonia",
                    "alcaldia": "Alcaldía",
                    "semaforo": "Semáforo",
                    "tasa_abatimiento_m_anio": "Bajada del nivel (m/año)",
                    "consejo_para_piperos": "Consejo",
                    "latitud": "Latitud",
                    "longitud": "Longitud",
                }
            )
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
