"""
ZASEVA — Centro de Inteligencia Hídrica (Corredor Poniente)
Fase A: textos legibles, semáforos en español, vista piperos, clic pozo ↔ mapa.
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
      .block-container { padding-top: 1.1rem; }
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


@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def try_load_supabase_table(table: str) -> pd.DataFrame | None:
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


def prepare_oferta(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    if "CLV_ACUI" in df.columns:
        df = df.rename(
            columns={
                "CLV_ACUI": "cve_acui",
                "NOM_ACUI": "nom_acui",
                "NOM_EDO": "nom_edo",
                "RECARGA_TO": "recarga_to_hm3",
                "DESCARGA_N": "descarga_n_hm3",
                "DMA_NEGATI": "dma_negati_hm3",
            }
        )
    if "cve_acui" in df.columns:
        df["cve_acui"] = df["cve_acui"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    if "deficit_hm3" not in df.columns and "dma_negati_hm3" in df.columns:
        df["deficit_hm3"] = df["dma_negati_hm3"].astype(float).abs()
    df["estatus"] = df["dma_negati_hm3"].astype(float).apply(
        lambda x: "🔴 En déficit" if x < 0 else "🟢 Con disponibilidad"
    )
    return df


def prepare_piezo(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    if "cve_acui" in df.columns:
        df["cve_acui"] = df["cve_acui"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    if "en_bbox_piloto" in df.columns:
        df = df[df["en_bbox_piloto"] == True].copy()  # noqa: E712
    if "n_obs" in df.columns:
        df = df[df["n_obs"] >= 2].copy()
    if "tasa_abatimiento_m_anio" in df.columns:
        df = df[df["tasa_abatimiento_m_anio"].notna()].copy()
    df["semaforo"] = df.get("nivel_estres", pd.Series(dtype=str)).map(semaforo_piezo)
    df["consejo_para_piperos"] = df.get("nivel_estres", pd.Series(dtype=str)).map(consejo_pipero)
    df["num_pozo"] = df["num_pozo"].astype(int)
    return df.reset_index(drop=True)


def main() -> None:
    st.title("ZASEVA")
    st.subheader("Centro de Inteligencia Hídrica — Corredor Poniente")
    st.markdown(
        """
        <p class="hint">
        Esta pantalla muestra <b>riesgo de agua</b> en Cuajimalpa, Álvaro Obregón y Huixquilucan
        con datos oficiales (CONAGUA / REPDA). Aún <b>no</b> incluye tiempos reales de carga de pipas
        (eso vendrá con la operación ZASEVA).
        </p>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("¿Qué estoy viendo? (guía rápida)", expanded=False):
        st.markdown(
            """
            - **Déficit de acuíferos:** el subsuelo está en números rojos (se saca más de lo que se recarga).
            - **Semáforo de pozos:** qué tan rápido baja el nivel del agua en puntos de medición.
            - **REPDA:** agua **autorizada legalmente** (no siempre igual a lo que se bombea hoy).
            - **Para piperos:** guía práctica de zonas a preferir o evitar, con lo que sabemos hoy.
            """
        )

    # ---- Datos ----
    oferta = try_load_supabase_table("v_oferta_acuifero")
    if oferta is None or oferta.empty:
        oferta = load_csv("oferta_acuiferos_poniente.csv")
    oferta = prepare_oferta(oferta)

    piezo_raw = try_load_supabase_table("v_heatmap_piezometria")
    if piezo_raw is None or piezo_raw.empty:
        piezo_raw = load_csv("estres_piezometrico_poniente.csv")
    piezo = prepare_piezo(piezo_raw)

    repda = try_load_supabase_table("v_repda_poniente")
    if repda is None or repda.empty:
        repda = load_csv("oferta_repda_poniente.csv")

    titles = load_csv("oferta_repda_poniente_titulos.csv")
    sequia = load_csv("riesgo_sequia_poniente.csv")

    # ---- KPIs ----
    deficit = float(oferta["deficit_hm3"].sum()) if len(oferta) else 0.0
    repda_hm3 = (
        float(titles["volumen_hm3_anio"].sum())
        if len(titles) and "volumen_hm3_anio" in titles.columns
        else 0.0
    )
    n_titles = len(titles) if len(titles) else 0
    piezo_critico = int(piezo["nivel_estres"].eq("ALTO").sum()) if len(piezo) else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Déficit de acuíferos", f"{deficit:,.0f} hm³/año", help="Agua que 'falta' al año en los acuíferos del piloto.")
    c2.metric("Agua concesionada (REPDA)", f"{repda_hm3:,.1f} hm³/año", help="Volumen autorizado en títulos, no bombeo medido en vivo.")
    c3.metric("Pozos en semáforo crítico", f"{piezo_critico}", help="Puntos donde el nivel baja más rápido.")
    c4.metric("Títulos REPDA en el piloto", f"{n_titles}", help="Cantidad de concesiones distintas en la zona.")

    st.divider()

    # ---- Selector de pozo (tabla → mapa) ----
    if "pozo_sel" not in st.session_state:
        st.session_state.pozo_sel = None

    pozo_opts = ["(Ver todo el mapa)"] + [
        f"{int(r.num_pozo)} · {r.semaforo} · {r.consejo_para_piperos}"
        for r in piezo.sort_values("tasa_abatimiento_m_anio", ascending=False).itertuples()
    ]
    sel = st.selectbox(
        "🔎 Buscar / enfocar un pozo en el mapa",
        options=pozo_opts,
        help="Elige un número de pozo para centrar el mapa ahí. También puedes usar las tablas de abajo.",
    )
    if sel and sel != "(Ver todo el mapa)":
        st.session_state.pozo_sel = int(sel.split("·")[0].strip())
    else:
        st.session_state.pozo_sel = None

    # ---- Mapa + panel derecho ----
    left, right = st.columns([1.65, 1], gap="large")

    with left:
        st.markdown("### Mapa del Corredor Poniente")
        st.caption(
            "Puntos de color = medición de nivel (estrés). Anillos = concesiones REPDA. "
            "Haz clic en un punto del mapa para ver detalle."
        )

        pmap = piezo.copy()
        # colores por semáforo
        color_map = {
            "ALTO": [196, 92, 38, 210],
            "MEDIO": [212, 160, 23, 200],
            "LEVE": [61, 124, 71, 190],
            "RECUPERACION_O_ESTABLE": [31, 122, 108, 190],
        }
        pmap["fill_color"] = pmap["nivel_estres"].map(
            lambda x: color_map.get(str(x).upper(), [120, 120, 120, 160])
        )
        pmap["radius"] = 90
        if st.session_state.pozo_sel is not None:
            pmap.loc[pmap["num_pozo"] == st.session_state.pozo_sel, "radius"] = 220

        layers = [
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
        ]

        if {"latitud", "longitud"}.issubset(repda.columns):
            rmap = repda.dropna(subset=["latitud", "longitud"]).copy()
            vol_col = (
                "volumen_punto_m3_anio"
                if "volumen_punto_m3_anio" in rmap.columns
                else "volumen_m3_anio"
            )
            vmax = max(float(rmap[vol_col].max()), 1.0) if vol_col in rmap.columns else 1.0
            rmap["radius"] = 35 + 160 * (rmap[vol_col] / vmax) ** 0.5 if vol_col in rmap.columns else 50
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=rmap,
                    id="repda",
                    get_position="[longitud, latitud]",
                    get_radius="radius",
                    stroked=True,
                    filled=False,
                    get_line_color="[11, 60, 77, 180]",
                    line_width_min_pixels=1,
                    pickable=True,
                )
            )

        # vista centrada en pozo seleccionado
        if st.session_state.pozo_sel is not None:
            row = pmap[pmap["num_pozo"] == st.session_state.pozo_sel].iloc[0]
            view = pdk.ViewState(
                latitude=float(row["latitud"]),
                longitude=float(row["longitud"]),
                zoom=13.2,
                pitch=0,
            )
        else:
            view = pdk.ViewState(latitude=19.35, longitude=-99.28, zoom=10.6, pitch=0)

        event = st.pydeck_chart(
            pdk.Deck(
                layers=layers,
                initial_view_state=view,
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                tooltip={
                    "html": "<b>Pozo {num_pozo}</b><br/>{semaforo}<br/>Bajada: {tasa_abatimiento_m_anio} m/año<br/>{consejo_para_piperos}",
                    "style": {"backgroundColor": "#0b3c4d", "color": "white"},
                },
            ),
            use_container_width=True,
            height=520,
            on_select="rerun",
            selection_mode="single-object",
            key="mapa_piloto",
        )

        # mapa → selección de pozo
        try:
            objects = event.selection.get("objects", {}) if event and event.selection else {}
            piezo_hits = objects.get("piezo") or objects.get("ScatterplotLayer") or []
            if piezo_hits:
                hit = piezo_hits[0]
                if "num_pozo" in hit:
                    st.session_state.pozo_sel = int(hit["num_pozo"])
                    st.info(
                        f"Seleccionado en mapa: **pozo {st.session_state.pozo_sel}** · "
                        f"{hit.get('semaforo', '')} · {hit.get('consejo_para_piperos', '')}"
                    )
        except Exception:
            pass

        if st.session_state.pozo_sel is not None:
            det = pmap[pmap["num_pozo"] == st.session_state.pozo_sel]
            if len(det):
                d = det.iloc[0]
                st.success(
                    f"**Pozo {int(d['num_pozo'])}** · {d['semaforo']} · "
                    f"Bajada del nivel: **{d['tasa_abatimiento_m_anio']:.2f} m/año** · "
                    f"{d['consejo_para_piperos']}"
                )

    with right:
        st.markdown("### Acuíferos (oferta de agua)")
        st.caption("Un acuífero es el ‘depósito’ subterráneo. Déficit = números rojos.")
        oferta_view = pd.DataFrame(
            {
                "Clave acuífero": oferta.get("cve_acui"),
                "Nombre del acuífero": oferta.get("nom_acui"),
                "Entidad": oferta.get("nom_edo"),
                "Recarga (hm³/año)": oferta.get("recarga_to_hm3"),
                "Déficit (hm³/año)": oferta.get("deficit_hm3"),
                "Estatus": oferta.get("estatus"),
            }
        )
        st.dataframe(oferta_view, use_container_width=True, hide_index=True)

        st.markdown("### Sequía oficial (municipios)")
        if len(sequia):
            sequia_view = pd.DataFrame(
                {
                    "Municipio": sequia.get("nombre_mun"),
                    "Entidad": sequia.get("entidad"),
                    "Semáforo sequía": sequia.get("sps"),
                    "Reducción pedida": sequia.get("ahorro_uso_eficiente"),
                }
            )
            st.dataframe(sequia_view, use_container_width=True, hide_index=True)
            st.caption("Si dice SIN SEQUÍA pero el acuífero está en déficit, el problema es estructural.")
        else:
            st.info("Sin datos de sequía.")

        st.markdown("### Agua concesionada por uso (REPDA)")
        if len(titles) and "uso" in titles.columns:
            uso = (
                titles.groupby("uso", dropna=False)["volumen_hm3_anio"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
                .rename(columns={"uso": "Uso del agua", "volumen_hm3_anio": "hm³ autorizados / año"})
            )
            st.bar_chart(uso, x="Uso del agua", y="hm³ autorizados / año", horizontal=True)

    st.divider()

    # ---- Vista piperos ----
    st.markdown("### Para piperos — ¿dónde conviene más?")
    st.caption(
        "Esto NO es un medidor de ‘tanque lleno’ en vivo. Es una guía de estrés del nivel freático: "
        "dónde el agua subterránea baja más rápido (evitar) vs más estable (preferible)."
    )

    preferir = piezo[piezo["nivel_estres"].isin(["RECUPERACION_O_ESTABLE", "LEVE"])].sort_values(
        "tasa_abatimiento_m_anio"
    )
    evitar = piezo[piezo["nivel_estres"] == "ALTO"].sort_values(
        "tasa_abatimiento_m_anio", ascending=False
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### ✅ Zonas / pozos más preferibles")
        pref_view = preferir.head(8)[
            ["num_pozo", "semaforo", "tasa_abatimiento_m_anio", "consejo_para_piperos", "latitud", "longitud"]
        ].rename(
            columns={
                "num_pozo": "No. pozo",
                "semaforo": "Semáforo",
                "tasa_abatimiento_m_anio": "Bajada del nivel (m/año)",
                "consejo_para_piperos": "Consejo",
                "latitud": "Latitud",
                "longitud": "Longitud",
            }
        )
        st.dataframe(pref_view, use_container_width=True, hide_index=True)
        if len(preferir):
            best = preferir.iloc[0]
            if st.button(f"Enfocar en mapa el pozo {int(best['num_pozo'])} (mejor de la lista)", key="btn_best"):
                st.session_state.pozo_sel = int(best["num_pozo"])
                st.rerun()

    with col_b:
        st.markdown("#### ⛔ Zonas / pozos a evitar (más críticos)")
        evit_view = evitar.head(8)[
            ["num_pozo", "semaforo", "tasa_abatimiento_m_anio", "consejo_para_piperos", "latitud", "longitud"]
        ].rename(
            columns={
                "num_pozo": "No. pozo",
                "semaforo": "Semáforo",
                "tasa_abatimiento_m_anio": "Bajada del nivel (m/año)",
                "consejo_para_piperos": "Consejo",
                "latitud": "Latitud",
                "longitud": "Longitud",
            }
        )
        st.dataframe(evit_view, use_container_width=True, hide_index=True)
        if len(evitar):
            worst = evitar.iloc[0]
            if st.button(f"Enfocar en mapa el pozo {int(worst['num_pozo'])} (más crítico)", key="btn_worst"):
                st.session_state.pozo_sel = int(worst["num_pozo"])
                st.rerun()

    st.divider()
    t1, t2 = st.tabs(["Lista completa de pozos (legible)", "Mayores títulos REPDA"])

    with t1:
        st.caption("Selecciona una fila para enfocar ese pozo en el mapa.")
        full = piezo.sort_values("tasa_abatimiento_m_anio", ascending=False).copy()
        full_view = full[
            ["num_pozo", "semaforo", "tasa_abatimiento_m_anio", "pne_ultimo_m", "consejo_para_piperos", "cve_acui", "latitud", "longitud"]
        ].rename(
            columns={
                "num_pozo": "No. pozo",
                "semaforo": "Semáforo",
                "tasa_abatimiento_m_anio": "Bajada del nivel (m/año)",
                "pne_ultimo_m": "Profundidad última medida (m)",
                "consejo_para_piperos": "Consejo para piperos",
                "cve_acui": "Clave acuífero",
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
            key="tabla_pozos",
        )
        try:
            rows = selected.selection.rows if selected and selected.selection else []
            if rows:
                idx = rows[0]
                st.session_state.pozo_sel = int(full.iloc[idx]["num_pozo"])
                st.write(f"Pozo enfocado: **{st.session_state.pozo_sel}** (mira el mapa arriba).")
        except Exception:
            pass

    with t2:
        src = titles if len(titles) else repda.drop_duplicates("titulo")
        if len(src) and "volumen_m3_anio" in src.columns:
            top = src.sort_values("volumen_m3_anio", ascending=False).head(10)
            top_view = pd.DataFrame(
                {
                    "Título / concesión": top.get("titulo"),
                    "Uso del agua": top.get("uso"),
                    "Volumen autorizado (m³/año)": top.get("volumen_m3_anio"),
                    "Titular": top.get("titular"),
                }
            )
            st.dataframe(top_view, use_container_width=True, hide_index=True)
            st.caption("REPDA = derecho legal de usar agua. No garantiza disponibilidad física inmediata.")

    with st.expander("Estado técnico de conexión"):
        has_db = False
        try:
            has_db = bool(st.secrets.get("SUPABASE_DB_URL"))
        except Exception:
            has_db = False
        if has_db:
            st.success("Conectado a Supabase (secret SUPABASE_DB_URL detectado).")
        else:
            st.info("Usando archivos CSV del proyecto. Supabase se conectará cuando pongamos el Secret.")


if __name__ == "__main__":
    main()
