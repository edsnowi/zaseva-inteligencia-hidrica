"""
ZASEVA — Centro de Inteligencia Hídrica (Corredor Poniente)
App Streamlit: lee CSV locales y, si hay secretos, también Supabase/PostGIS.
"""

from __future__ import annotations

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
      .block-container { padding-top: 1.2rem; }
      h1, h2, h3 { font-family: Georgia, serif; color: #0b3c4d; }
      div[data-testid="stMetricValue"] { color: #0b3c4d; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def try_load_supabase_table(table: str) -> pd.DataFrame | None:
    """Si hay SUPABASE_DB_URL en secrets, lee una tabla; si no, None."""
    url = None
    try:
        url = st.secrets.get("SUPABASE_DB_URL")
    except Exception:
        url = None
    if not url:
        return None
    try:
        from sqlalchemy import create_engine

        engine = create_engine(url)
        return pd.read_sql(f"SELECT * FROM zaseva.{table}", engine)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"No pude leer Supabase ({table}): {exc}")
        return None


def main() -> None:
    st.title("ZASEVA")
    st.subheader("Centro de Inteligencia Hídrica — Corredor Poniente")
    st.caption(
        "Cuajimalpa · Álvaro Obregón · Huixquilucan — acuíferos CONAGUA, "
        "piezometría, REPDA. Sin telemetría de viajes aún."
    )

    # Datos: preferir Supabase si existe; si no, CSV
    oferta = try_load_supabase_table("v_oferta_acuifero") 
    if oferta is None or oferta.empty:
        oferta = load_csv("oferta_acuiferos_poniente.csv")
        # normalizar nombres si vienen del CSV crudo
        if "CLV_ACUI" in oferta.columns:
            oferta = oferta.rename(
                columns={
                    "CLV_ACUI": "cve_acui",
                    "NOM_ACUI": "nom_acui",
                    "NOM_EDO": "nom_edo",
                    "RECARGA_TO": "recarga_to_hm3",
                    "DESCARGA_N": "descarga_n_hm3",
                    "DMA_NEGATI": "dma_negati_hm3",
                }
            )
            oferta["deficit_hm3"] = oferta["dma_negati_hm3"].abs()

    piezo = try_load_supabase_table("v_heatmap_piezometria")
    if piezo is None or piezo.empty:
        piezo = load_csv("estres_piezometrico_poniente.csv")

    repda = try_load_supabase_table("v_repda_poniente")
    if repda is None or repda.empty:
        repda = load_csv("oferta_repda_poniente.csv")

    titles = load_csv("oferta_repda_poniente_titulos.csv")
    sequia = load_csv("riesgo_sequia_poniente.csv")

    # KPIs
    deficit = float(oferta["deficit_hm3"].sum()) if "deficit_hm3" in oferta.columns else float(
        oferta.get("dma_negati_hm3", pd.Series([0])).abs().sum()
    )
    repda_hm3 = (
        float(titles["volumen_hm3_anio"].sum())
        if len(titles) and "volumen_hm3_anio" in titles.columns
        else float(repda.get("volumen_hm3_anio", pd.Series([0])).sum())
    )
    n_titles = len(titles) if len(titles) else repda["titulo"].nunique() if "titulo" in repda.columns else 0
    piezo_alto = int((piezo.get("nivel_estres") == "ALTO").sum()) if "nivel_estres" in piezo.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Déficit acuíferos", f"{deficit:,.0f} hm³/año")
    c2.metric("REPDA autorizado", f"{repda_hm3:,.1f} hm³/año")
    c3.metric("Pozos estrés ALTO", f"{piezo_alto}")
    c4.metric("Títulos REPDA", f"{n_titles}")

    st.divider()

    left, right = st.columns([1.7, 1])

    with left:
        st.markdown("### Mapa del piloto")
        st.caption("Puntos piezométricos (color = abatimiento) y concesiones REPDA.")

        map_layers = []
        # Piezo
        if {"latitud", "longitud"}.issubset(piezo.columns):
            pmap = piezo.dropna(subset=["latitud", "longitud"]).copy()
            if "en_bbox_piloto" in pmap.columns:
                pmap = pmap[pmap["en_bbox_piloto"] == True]  # noqa: E712
            if "tasa_abatimiento_m_anio" in pmap.columns:
                pmap = pmap[pmap["tasa_abatimiento_m_anio"].notna()]
                pmap["heat_weight"] = pmap["tasa_abatimiento_m_anio"].clip(lower=0)
            else:
                pmap["heat_weight"] = 1.0
            map_layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=pmap,
                    get_position="[longitud, latitud]",
                    get_radius=80,
                    get_fill_color="[196, 92, 38, 180]",
                    pickable=True,
                )
            )

        # REPDA
        if {"latitud", "longitud"}.issubset(repda.columns):
            rmap = repda.dropna(subset=["latitud", "longitud"]).copy()
            vol_col = (
                "volumen_punto_m3_anio"
                if "volumen_punto_m3_anio" in rmap.columns
                else "volumen_m3_anio"
            )
            if vol_col in rmap.columns:
                vmax = max(float(rmap[vol_col].max()), 1.0)
                rmap["radius"] = 40 + 200 * (rmap[vol_col] / vmax) ** 0.5
            else:
                rmap["radius"] = 60
            map_layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=rmap,
                    get_position="[longitud, latitud]",
                    get_radius="radius",
                    stroked=True,
                    filled=False,
                    get_line_color="[11, 60, 77, 200]",
                    line_width_min_pixels=1,
                    pickable=True,
                )
            )

        view = pdk.ViewState(latitude=19.35, longitude=-99.28, zoom=10.5, pitch=0)
        st.pydeck_chart(
            pdk.Deck(
                layers=map_layers,
                initial_view_state=view,
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                tooltip={"text": "Lat: {latitud}\nLon: {longitud}"},
            ),
            use_container_width=True,
            height=520,
        )

    with right:
        st.markdown("### Acuíferos (oferta)")
        show_cols = [
            c
            for c in ["cve_acui", "nom_acui", "recarga_to_hm3", "dma_negati_hm3", "deficit_hm3"]
            if c in oferta.columns
        ]
        st.dataframe(oferta[show_cols] if show_cols else oferta, use_container_width=True, hide_index=True)

        st.markdown("### Sequía municipal")
        if len(sequia):
            st.dataframe(
                sequia[
                    [c for c in ["nombre_mun", "entidad", "sps", "ahorro_uso_eficiente"] if c in sequia.columns]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Sin datos de sequía cargados.")

        st.markdown("### REPDA por uso")
        if len(titles) and "uso" in titles.columns:
            uso = (
                titles.groupby("uso", dropna=False)["volumen_hm3_anio"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            st.bar_chart(uso, x="uso", y="volumen_hm3_anio", horizontal=True)
        elif "uso" in repda.columns and "volumen_hm3_anio" in repda.columns:
            uso = (
                repda.drop_duplicates("titulo")
                .groupby("uso")["volumen_hm3_anio"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            st.bar_chart(uso, x="uso", y="volumen_hm3_anio", horizontal=True)

    st.divider()
    t1, t2 = st.tabs(["Top abatimiento", "Top títulos REPDA"])
    with t1:
        if "tasa_abatimiento_m_anio" in piezo.columns:
            top = piezo.copy()
            if "en_bbox_piloto" in top.columns:
                top = top[top["en_bbox_piloto"] == True]  # noqa: E712
            top = top.sort_values("tasa_abatimiento_m_anio", ascending=False).head(10)
            cols = [
                c
                for c in [
                    "num_pozo",
                    "cve_acui",
                    "tasa_abatimiento_m_anio",
                    "nivel_estres",
                    "latitud",
                    "longitud",
                ]
                if c in top.columns
            ]
            st.dataframe(top[cols], use_container_width=True, hide_index=True)
    with t2:
        src = titles if len(titles) else repda.drop_duplicates("titulo")
        if "volumen_m3_anio" in src.columns:
            top = src.sort_values("volumen_m3_anio", ascending=False).head(10)
            cols = [c for c in ["titulo", "uso", "volumen_m3_anio", "titular"] if c in top.columns]
            st.dataframe(top[cols], use_container_width=True, hide_index=True)

    with st.expander("Estado de conexión"):
        has_db = False
        try:
            has_db = bool(st.secrets.get("SUPABASE_DB_URL"))
        except Exception:
            has_db = False
        if has_db:
            st.success("Secret SUPABASE_DB_URL detectado — intentando leer tablas zaseva.*")
        else:
            st.info(
                "Ahora mismo la app usa los CSV de la carpeta data/. "
                "Cuando cargues PostGIS en Supabase y pongas el secret, leerá la base."
            )


if __name__ == "__main__":
    main()
