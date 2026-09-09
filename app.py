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
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "zaseva_logo.png"
MARK_PATH = ASSETS_DIR / "zaseva_mark.png"

st.set_page_config(
    page_title="ZASEVA · Inteligencia Hídrica",
    page_icon=str(MARK_PATH) if MARK_PATH.exists() else "💧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      :root {
        --z-bg: #05070c;
        --z-panel: #0b1220;
        --z-card: #121a2b;
        --z-border: #1e3a5f;
        --z-muted: #8aa4bd;
        --z-text: #e8f1fa;
        --z-accent: #2f6bff;
        --z-accent-2: #a855f7;
        --z-ok: #22c55e;
        --z-bad: #ef4444;
      }
      /* Fondo oscuro tipo Asterra / sala de venta */
      .stApp { background: radial-gradient(1200px 600px at 10% -10%, #12203a 0%, var(--z-bg) 55%) !important; color: var(--z-text); }
      .block-container { padding-top: 1rem; padding-bottom: 2.4rem; max-width: 1400px; }
      header[data-testid="stHeader"] { background: rgba(5,7,12,0.85); }
      [data-testid="stToolbar"] { background: transparent; }
      h1, h2, h3, h4 { font-family: "Segoe UI", Inter, system-ui, sans-serif !important; color: #f8fafc !important; letter-spacing: -0.02em; }
      p, label, .stMarkdown, .stCaption, span, div { color: #d7e3f0; }
      .hint { color: #9db0c5; font-size: 0.92rem; line-height: 1.45; }
      div[data-testid="stMetricValue"] { color: #f8fafc !important; }
      div[data-testid="stMetricLabel"] { color: #9db0c5 !important; }
      [data-testid="stExpander"] {
        background: var(--z-panel); border: 1px solid var(--z-border); border-radius: 12px;
      }
      [data-testid="stDataFrame"], [data-testid="stTable"] {
        background: var(--z-panel); border: 1px solid var(--z-border); border-radius: 12px;
      }
      .stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 1px solid #1e293b; }
      .stTabs [data-baseweb="tab"] {
        background: #0f172a; color: #cbd5e1; border-radius: 10px 10px 0 0;
        border: 1px solid #1e293b; padding: 8px 14px;
      }
      .stTabs [aria-selected="true"] {
        background: linear-gradient(180deg, #1d4ed8 0%, #1e3a8a 100%) !important;
        color: #fff !important; border-color: #2563eb !important;
      }
      .z-hero {
        display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
        margin: 0 0 14px 0; padding: 10px 4px 4px 4px;
      }
      .z-hero-copy { max-width: 760px; }
      .z-kicker {
        font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase; color: #7eb6ff;
        margin-bottom: 4px;
      }
      .z-banner {
        background: linear-gradient(90deg, #1d4ed8 0%, #2563eb 60%, #3b82f6 100%);
        color: #fff; border-radius: 12px; padding: 14px 16px; margin: 8px 0 14px 0;
        display:flex; align-items:center; justify-content:space-between; gap:12px;
        box-shadow: 0 10px 30px rgba(37,99,235,0.25);
      }
      .z-banner h4 { margin:0; color:#fff !important; font-size:1.05rem; }
      .z-banner p { margin:4px 0 0 0; color:#dbeafe; font-size:0.86rem; }
      .z-scoreboard {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 14px;
        margin: 0.35rem 0 0.9rem 0;
      }
      .z-scoreboard.stack {
        grid-template-columns: 1fr;
        gap: 14px;
        margin: 0.2rem 0 1.1rem 0;
      }
      .z-card {
        background: linear-gradient(180deg, #152238 0%, #101827 100%);
        border: 1px solid var(--z-border); border-radius: 14px;
        padding: 14px 16px; color: #e8f1fa; min-height: 86px;
      }
      .z-scoreboard.stack .z-card { min-height: 100px; padding: 18px 20px; }
      .z-scoreboard.stack .z-card .val { font-size: 1.7rem; }
      .z-legend {
        display:flex; flex-wrap:wrap; gap:10px; margin: 0 0 12px 0;
      }
      .z-chip {
        border-radius: 999px; padding: 6px 12px; font-size: 0.78rem; border: 1px solid #334155;
        background: #0f172a; color: #cbd5e1;
      }
      .z-chip.ok { border-color:#16a34a; color:#86efac; }
      .z-chip.warn { border-color:#ca8a04; color:#fde68a; }
      .z-chip.bad { border-color:#dc2626; color:#fca5a5; }
      .z-chip.info { border-color:#2563eb; color:#93c5fd; }
      .z-card .lbl {
        font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--z-muted);
      }
      .z-card .val { font-size: 1.55rem; font-weight: 700; margin-top: 6px; color: #f8fafc; line-height: 1.15; word-break: break-word; }
      .z-card .sub { font-size: 0.8rem; color: #94a3b8; margin-top: 4px; line-height: 1.35; }
      .z-pipa {
        border-radius: 12px; padding: 14px 16px; margin-bottom: 10px; border: 1px solid #334155;
        background: #0f172a; color: #e2e8f0;
      }
      .z-pipa.ok { border-color: #16a34a; box-shadow: inset 4px 0 0 #22c55e; }
      .z-pipa.warn { border-color: #ca8a04; box-shadow: inset 4px 0 0 #eab308; }
      .z-pipa.bad { border-color: #dc2626; box-shadow: inset 4px 0 0 #ef4444; }
      .z-pipa .title { font-weight: 700; font-size: 1rem; color:#f8fafc; }
      .z-pipa .meta { font-size: 0.84rem; color: #94a3b8; margin-top: 4px; line-height: 1.4; }
      .z-explain {
        background: #0f172a; border: 1px solid #1e293b; border-radius: 12px;
        padding: 12px 14px; color: #cbd5e1; font-size: 0.9rem; margin-bottom: 12px;
      }
      @media (max-width: 768px) {
        .block-container { padding-left: 0.7rem !important; padding-right: 0.7rem !important; }
        .z-scoreboard { grid-template-columns: 1fr; gap: 10px; }
        .z-card .val { font-size: 1.25rem; }
        div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 0.35rem !important; }
        div[data-testid="column"] { width: 100% !important; min-width: 100% !important; flex: 1 1 100% !important; }
        section.main .stMarkdown, section.main .stDataFrame { overflow-x: auto; }
      }
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


def norm_alcaldia(series: pd.Series) -> pd.Series:
    """Normaliza nombres de alcaldía para matching B2G (strip + lower + sin acentos simples)."""
    s = series.fillna("").astype(str).str.strip().str.lower()
    repl = (
        ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
        ("ü", "u"), ("ñ", "n"),
    )
    for a, b in repl:
        s = s.str.replace(a, b, regex=False)
    return s.str.replace(r"\s+", " ", regex=True)


def map_height_responsive() -> int:
    """Altura del mapa: más baja en móvil para no bloquear el scroll táctil."""
    try:
        # st.context.headers existe en Streamlit recientes
        ua = str(st.context.headers.get("User-Agent", "")).lower()  # type: ignore[attr-defined]
        if any(x in ua for x in ("iphone", "android", "mobile", "ipad")):
            return 380
    except Exception:
        pass
    return 560


def enrich_sar_pfs(smap: pd.DataFrame) -> pd.DataFrame:
    """
    PFS (Pipe Failure Score) 0–100 sobre puntos SAR filtrados.
    PFS = min(100, round(|delta_db|/10 * 50 + max(0, 1 - dist_m/2000) * 50))
    """
    out = smap.copy()
    delta_col = next((c for c in ("delta_db", "delta_db", "delta_db") if c in out.columns), None)
    dist_col = next(
        (c for c in ("dist_pozo_critico_m", "dist_pozo_critico_m", "dist_pozo_critico_m") if c in out.columns),
        None,
    )
    bs_col = next((c for c in ("backscatter_db", "backscatter_db", "backscatter_db") if c in out.columns), None)
    delta = (
        pd.to_numeric(out[delta_col], errors="coerce").fillna(0.0).abs()
        if delta_col is not None
        else pd.Series(0.0, index=out.index)
    )
    dist = (
        pd.to_numeric(out[dist_col], errors="coerce").fillna(2000.0).clip(lower=0)
        if dist_col is not None
        else pd.Series(2000.0, index=out.index)
    )
    pfs = ((delta / 10.0) * 50.0 + (1.0 - (dist / 2000.0)).clip(lower=0) * 50.0).round().clip(upper=100)
    out["pfs"] = pfs.astype(int)
    out["delta_db_tip"] = delta.round(2)
    out["dist_pozo_m_tip"] = dist.round(0).astype(int)
    out["backscatter_tip"] = (
        pd.to_numeric(out[bs_col], errors="coerce").round(1)
        if bs_col is not None
        else pd.Series([pd.NA] * len(out), index=out.index)
    )
    out["fill_color"] = out["pfs"].map(
        lambda v: [239, 68, 68, 200] if int(v) >= 70 else [168, 85, 247, 160]
    )
    out["line_color"] = out["pfs"].map(
        lambda v: [254, 202, 202, 220] if int(v) >= 70 else [233, 213, 255, 200]
    )
    out["radius"] = 45
    return out


def scoreboard_html(cards: list[tuple[str, str, str]], *, stack: bool = False) -> str:
    """Tarjetas ejecutivas oscuras. stack=True apila vertical (panel lateral)."""
    cells = []
    for lbl, val, sub in cards:
        cells.append(
            f'<div class="z-card"><div class="lbl">{lbl}</div>'
            f'<div class="val">{val}</div><div class="sub">{sub}</div></div>'
        )
    klass = "z-scoreboard stack" if stack else "z-scoreboard"
    return f'<div class="{klass}">{"".join(cells)}</div>'


def section_banner(title: str, subtitle: str) -> str:
    """Banner azul tipo Asterra para abrir cada bloque técnico."""
    return (
        f'<div class="z-banner"><div><h4>{title}</h4>'
        f'<p>{subtitle}</p></div></div>'
    )


def explain_box(text: str) -> str:
    return f'<div class="z-explain">{text}</div>'


def pipero_card_html(titulo: str, meta: str, kind: str = "ok") -> str:
    return (
        f'<div class="z-pipa {kind}"><div class="title">{titulo}</div>'
        f'<div class="meta">{meta}</div></div>'
    )


def _hex_blend(t: float, c0: tuple[int, int, int], c1: tuple[int, int, int]) -> str:
    t = max(0.0, min(1.0, float(t)))
    rgb = tuple(int(a + (b - a) * t) for a, b in zip(c0, c1))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def paint_priority_table(
    df: pd.DataFrame,
    *,
    score_cols: list[str] | None = None,
    risk_cols: list[str] | None = None,
):
    """Colorea tablas técnicas (fondo oscuro + semáforo de prioridad)."""
    if df is None or getattr(df, "empty", True):
        return df
    score_cols = [c for c in (score_cols or []) if c in df.columns]
    risk_cols = [c for c in (risk_cols or []) if c in df.columns]
    sty = df.style.set_properties(
        **{
            "background-color": "#0b1220",
            "color": "#e2e8f0",
            "border-color": "#1e293b",
            "font-size": "0.92rem",
        }
    )
    sty = sty.set_table_styles(
        [
            {
                "selector": "th",
                "props": [
                    ("background-color", "#1d4ed8"),
                    ("color", "#ffffff"),
                    ("font-weight", "600"),
                    ("border-color", "#1e3a8a"),
                    ("text-align", "left"),
                ],
            }
        ]
    )

    def _score_color(v):
        try:
            x = float(v)
        except Exception:
            return "background-color:#0b1220;color:#e2e8f0"
        bg = _hex_blend(x / 100.0, (37, 99, 235), (220, 38, 38))
        return f"background-color:{bg};color:#fff;font-weight:700"

    def _risk_color(v):
        s = str(v).upper() if pd.notna(v) else ""
        if "ALTO" in s or "CRÍT" in s or "CRIT" in s or "ROJO" in s:
            return "background-color:#7f1d1d;color:#fecaca;font-weight:700"
        if "MEDIO" in s or "NARANJA" in s or "ÁMBAR" in s or "AMBAR" in s:
            return "background-color:#78350f;color:#fde68a;font-weight:600"
        if "LEVE" in s or "BAJO" in s or "VERDE" in s or "ESTABLE" in s or "RECUPER" in s:
            return "background-color:#14532d;color:#bbf7d0;font-weight:600"
        if "🔴" in str(v):
            return "background-color:#7f1d1d;color:#fecaca;font-weight:700"
        if "🟠" in str(v) or "🟡" in str(v):
            return "background-color:#78350f;color:#fde68a;font-weight:600"
        if "🟢" in str(v):
            return "background-color:#14532d;color:#bbf7d0;font-weight:600"
        return "background-color:#0b1220;color:#e2e8f0"

    def _apply(styler, fn, subset):
        if hasattr(styler, "map"):
            return styler.map(fn, subset=subset)
        return styler.applymap(fn, subset=subset)

    for col in score_cols:
        sty = _apply(sty, _score_color, [col])
    for col in risk_cols:
        sty = _apply(sty, _risk_color, [col])
    return sty


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
            out = out.copy()
            out["_k"] = norm_alcaldia(out["alcaldia"])
            meta["_k"] = norm_alcaldia(meta["alcaldia"])
            meta = meta.drop(columns=["alcaldia"])
            out = out.merge(meta, on="_k", how="left", suffixes=("", "_diag"))
            out = out.drop(columns=["_k"], errors="ignore")
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
        keys = set(norm_alcaldia(pd.Series(list(alcaldias_filtro))))
        matched = out[norm_alcaldia(out["alcaldia"]).isin(keys)]
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
    # Header de marca (logo + propuesta de valor)
    c_logo, c_copy = st.columns([1.1, 2.4], gap="large")
    with c_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
        elif MARK_PATH.exists():
            st.image(str(MARK_PATH), width=120)
        else:
            st.markdown("### zaseva")
    with c_copy:
        st.markdown(
            """
            <div class="z-kicker">Centro de inteligencia hídrica · CDMX</div>
            <h2 style="margin:0 0 6px 0;">Sala de situación para decisión B2G</h2>
            <p class="hint" style="margin:0;">
            Radar Sentinel-1 + pozos oficiales + REPDA en un solo lienzo.
            Prioriza inspección, conversa con alcaldías y opera la flota con evidencia.
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
            - **Prioridad de inspección (0–100):** dónde conviene mandar brigada primero (no es fuga confirmada).
            - **Para piperos:** guía de carga preferible vs evitar (proxy de estrés del pozo, no nivel de tanque).
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

    st.markdown(
        scoreboard_html(
            [
                ("Déficit acuíferos CDMX", f"{deficit:,.0f} hm³/año", "CONAGUA · estructura"),
                ("Agua concesionada", f"{repda_hm3:,.1f} hm³/año", "REPDA · filtro actual"),
                ("Pozos críticos", f"{piezo_critico}", "Abatimiento ALTO"),
                ("Títulos REPDA", f"{n_titles}", "Derechos formales"),
                ("Señales SAR", f"{sar_count}", "Humedad anómala · mapa"),
            ]
        ),
        unsafe_allow_html=True,
    )
    if piezo_critico:
        st.caption(
            f"Hay **{piezo_critico} pozos críticos (ALTO)** en el filtro: "
            "el detalle técnico queda en pestañas al final (no bloquea la sala de situación)."
        )
    if score_max > 0:
        st.caption(f"Prioridad máxima de inspección en el filtro: **{score_max:.0f}/100** (brigada primero).")

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

    # Detalle de pozos críticos se muestra al final (pestañas), no antes del mapa
    crit_tabla = enrich_critical_wells(pie_mapa if len(pie_mapa) else pie)

    left, right = st.columns([1.65, 1], gap="large")
    hum = pd.DataFrame()  # se llena en el panel derecho; disponible para pestañas B2G

    with left:
        st.markdown("### Mapa")
        st.caption(
            "**Morado = humedad anómala · Rojo fuego = PFS ≥ 70 (prioridad de inspección).** "
            "Hoy el satélite cubre sobre todo el **Corredor Poniente**. "
            "Tooltip: alcaldía, PFS, Δ dB y distancia al pozo crítico."
        )
        with st.expander("Leyenda (plática con alcaldías)", expanded=False):
            st.markdown(
                """
                | Color | Significa |
                |---|---|
                | **Morado** | Humedad anómala Sentinel-1 (PFS &lt; 70) — alerta de inspección |
                | **Rojo fuego** | PFS ≥ 70 — prioridad alta de inspección de red |
                | **Rojo (pozo)** | Pozo abatimiento ALTO |
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
            if smap.empty and len(sar_map):
                smap = sar_map.dropna(subset=["latitud", "longitud"]).copy()
            smap = enrich_sar_pfs(smap)
            if "colonia" not in smap.columns:
                smap["colonia"] = ""
            smap["tip_titulo"] = smap["pfs"].map(
                lambda v: f"SAR · PFS {int(v)}/100" + (" · ALERTA ALTA" if int(v) >= 70 else "")
            )
            smap["tip_linea1"] = smap.apply(
                lambda r: f"{r.get('alcaldia', '')} · {r.get('colonia', '')}".strip(" ·"),
                axis=1,
            )
            smap["tip_linea2"] = smap.apply(
                lambda r: (
                    f"Δ {float(r['delta_db_tip']):.1f} dB"
                    + (f" · σ0 {float(r['backscatter_tip']):.1f} dB" if pd.notna(r.get('backscatter_tip')) else "")
                    + f" · pozo crítico a {int(r['dist_pozo_m_tip'])} m"
                ),
                axis=1,
            )
            smap["tip_linea3"] = smap.apply(
                lambda r: "Vecinos ALTO: " + nearest_points_text(
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
                    radius_min_pixels=3,
                    radius_max_pixels=14,
                    get_fill_color="fill_color",
                    get_line_color="line_color",
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
            height=map_height_responsive(),
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
            "Más puntos = más urgente revisar la red."
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
            total_h = int(hum["humedades_anomalas"].sum())
            st.markdown(
                scoreboard_html(
                    [
                        ("Señales en foco", f"{total_h}", "conteo SAR real del mapa"),
                        ("Alcaldía prioridad", str(top["alcaldia"]), str(top.get("prioridad", ""))),
                        ("Máx. en una alcaldía", f"{int(top['humedades_anomalas'])}", "puntos concentrados"),
                    ],
                    stack=True,
                ),
                unsafe_allow_html=True,
            )
            hum_view = hum.rename(
                columns={
                    "alcaldia": "Alcaldía / municipio",
                    "humedades_anomalas": "Señales SAR (humedad anómala)",
                    "score_severidad_max": "Prioridad máx. de inspección",
                    "nivel_riesgo_estructural": "Riesgo territorial",
                    "prioridad": "Orden de revisión",
                }
            )
            chart_df = hum_view.head(8).copy()
            if "Señales SAR (humedad anómala)" in chart_df.columns:
                st.bar_chart(
                    chart_df,
                    x="Alcaldía / municipio",
                    y="Señales SAR (humedad anómala)",
                    horizontal=True,
                )
            with st.expander("Tabla detallada por alcaldía", expanded=False):
                st.dataframe(hum_view, use_container_width=True, hide_index=True, height=280)
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
    st.markdown(
        section_banner(
            "Inspección municipal · detalle técnico",
            "Secuencia de venta: 1) prioriza con SAR · 2) valida pozos · 3) contextualiza REPDA · 4) opera flota",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        explain_box(
            "<b>Qué le mostramos al cliente:</b> no es un reporte técnico crudo. "
            "Es la bitácora para decidir <b>dónde abrir inspección</b>, "
            "<b>qué pozos cruzar</b>, <b>qué presión legal hay (REPDA)</b> y "
            "<b>cómo responder con pipas</b>."
        ),
        unsafe_allow_html=True,
    )

    tab_sar, tab_pozos, tab_repda, tab_piperos = st.tabs(
        ["1 · Inspección SAR", "2 · Auditoría de pozos", "3 · Concesiones REPDA", "4 · Módulo piperos"]
    )

    with tab_sar:
        st.markdown(
            section_banner(
                "Inspección SAR · radar de humedad anómala",
                "Primero el resumen por alcaldía; después la cola de colonias para mandar brigada.",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            explain_box(
                "<b>Cómo leer esta pestaña:</b> el color azul→rojo en el score es <b>prioridad de visita</b>, "
                "no una fuga ya confirmada. Úsalo para armar la ruta de inspección con la alcaldía."
            ),
            unsafe_allow_html=True,
        )
        if len(diagnostico):
            diag = diagnostico.copy()
            if "hum" in dir() and len(hum) and "alcaldia" in hum.columns and "alcaldia" in diag.columns:
                h2 = hum.copy()
                h2["_k"] = norm_alcaldia(h2["alcaldia"])
                diag["_k"] = norm_alcaldia(diag["alcaldia"])
                diag = diag.merge(
                    h2[["_k", "humedades_anomalas"]].rename(columns={"humedades_anomalas": "fugas_sar_reales"}),
                    on="_k",
                    how="left",
                )
                if "puntos_criticos_fugas" in diag.columns:
                    diag["puntos_criticos_fugas"] = (
                        pd.to_numeric(diag["fugas_sar_reales"], errors="coerce")
                        .fillna(pd.to_numeric(diag["puntos_criticos_fugas"], errors="coerce"))
                        .fillna(0)
                        .astype(int)
                    )
                diag = diag.drop(columns=["_k", "fugas_sar_reales"], errors="ignore")
            n_alc = len(diag)
            sig_col = "puntos_criticos_fugas" if "puntos_criticos_fugas" in diag.columns else None
            sc_col = "score_severidad_max" if "score_severidad_max" in diag.columns else None
            total_sig = int(pd.to_numeric(diag[sig_col], errors="coerce").fillna(0).sum()) if sig_col else 0
            max_sc = float(pd.to_numeric(diag[sc_col], errors="coerce").max()) if sc_col else 0.0
            st.markdown(
                scoreboard_html(
                    [
                        ("Alcaldías en vista", f"{n_alc}", "universo del filtro"),
                        ("Señales SAR", f"{total_sig:,}", "humedad anómala agregada"),
                        ("Prioridad máx.", f"{max_sc:.0f}/100" if max_sc else "—", "dónde abrir primero"),
                    ]
                ),
                unsafe_allow_html=True,
            )
            rename_diag = {
                "alcaldia": "Alcaldía",
                "puntos_criticos_fugas": "Señales SAR",
                "deficit_acuifero_hm3_promedio": "Déficit acuífero (hm³)",
                "score_severidad_promedio": "Prioridad promedio",
                "score_severidad_max": "Prioridad máxima",
                "nivel_riesgo_estructural": "Riesgo territorial",
                "n_colonias": "Colonias",
            }
            diag_view = diag.rename(columns={k: v for k, v in rename_diag.items() if k in diag.columns})
            st.markdown("##### Resumen por alcaldía")
            st.dataframe(
                paint_priority_table(
                    diag_view,
                    score_cols=["Prioridad promedio", "Prioridad máxima"],
                    risk_cols=["Riesgo territorial"],
                ),
                use_container_width=True,
                hide_index=True,
                height=320,
            )
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
            st.markdown("##### Cola de brigada · colonias / celdas calientes")
            st.markdown(
                explain_box(
                    "Esto es lo que antes se leía como “score de severidad”. "
                    "Traducción comercial: <b>lista ordenada de sitios a inspeccionar primero</b>. "
                    "Cada fila = una colonia/celda candidata a visita de campo."
                ),
                unsafe_allow_html=True,
            )
            top = salud.head(25).rename(
                columns={
                    "colonia": "Colonia (prioridad de visita)",
                    "alcaldia": "Alcaldía",
                    "score_severidad_fuga": "Prioridad de inspección (0-100)",
                    "nivel_riesgo_red": "Nivel de riesgo",
                    "score_sar_humedad": "Señal humedad SAR",
                    "score_abatimiento": "Estrés de pozo",
                    "deficit_acui_hm3": "Déficit acuífero hm³",
                    "fecha_calculo": "Fecha de cálculo",
                }
            )
            st.dataframe(
                paint_priority_table(
                    top,
                    score_cols=[
                        "Prioridad de inspección (0-100)",
                        "Señal humedad SAR",
                        "Estrés de pozo",
                    ],
                    risk_cols=["Nivel de riesgo"],
                ),
                use_container_width=True,
                hide_index=True,
                height=360,
            )

    with tab_pozos:
        st.markdown(
            section_banner(
                "Auditoría de pozos · semáforo de estrés",
                "Rojo = crítico · Naranja = precaución · Verde = preferible para operación / pipas.",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            explain_box(
                "<b>Para la mesa técnica:</b> muestra abatimiento y alternativa cercana. "
                "Sirve para justificar por qué un pozo entra a bitácora o por qué conviene evitarlo."
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="z-legend">'
            '<span class="z-chip bad">Rojo · evitar / crítico</span>'
            '<span class="z-chip warn">Ámbar · precaución</span>'
            '<span class="z-chip ok">Verde · preferible</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown("##### Lista prioritaria (ALTO)")
        if len(crit_tabla):
            n_crit = len(crit_tabla)
            st.markdown(
                scoreboard_html(
                    [
                        ("Pozos críticos", f"{n_crit}", "abatimiento ALTO en filtro"),
                        (
                            "Peor bajada",
                            f"{float(crit_tabla['tasa_abatimiento_m_anio'].max()):.2f} m/año"
                            if "tasa_abatimiento_m_anio" in crit_tabla.columns
                            else "—",
                            "máximo del filtro",
                        ),
                        (
                            "Con alternativa",
                            f"{int(crit_tabla['recomendacion_cercana'].notna().sum())}"
                            if "recomendacion_cercana" in crit_tabla.columns
                            else "—",
                            "pozo preferible cercano",
                        ),
                    ],
                ),
                unsafe_allow_html=True,
            )
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
                "recomendacion_cercana": "Alternativa preferible",
                "dist_recomendacion_km": "Dist. km",
                "latitud": "Lat",
                "longitud": "Lon",
            })
            st.dataframe(
                paint_priority_table(crit_view, risk_cols=["Semáforo"]),
                use_container_width=True,
                hide_index=True,
                height=320,
            )
        else:
            st.write("Sin pozos críticos en este filtro.")
        st.markdown("##### Inventario completo del filtro")
        st.caption("Haz clic en una fila para enfocar el pozo en el mapa.")
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

    with tab_repda:
        st.markdown(
            section_banner(
                "Concesiones REPDA · presión legal sobre el acuífero",
                "Quién tiene derecho a extraer y cuánto volumen está autorizado en la zona.",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            explain_box(
                "<b>Narrativa B2G:</b> aunque existan títulos vigentes, el sistema puede estar estresado "
                "(pozos ALTO + humedad SAR). Esta tabla es el marco documental que acompaña al mapa físico."
            ),
            unsafe_allow_html=True,
        )
        if len(titles):
            tfilt = titles.copy()
            if ambito == "Corredor Poniente" and "en_poniente" in tfilt.columns:
                tfilt = tfilt[tfilt["en_poniente"] == True]  # noqa: E712
            if seleccion_alcaldias and "alcaldia" in tfilt.columns:
                tfilt = tfilt[tfilt["alcaldia"].isin(seleccion_alcaldias)]
            if filtro_colonias_activo and "colonia" in tfilt.columns:
                tfilt = tfilt[tfilt["colonia"].isin(colonia_sel_rows["colonia"].unique())]
            vol_col = "volumen_m3_anio" if "volumen_m3_anio" in tfilt.columns else (
                "volumen_hm3_anio" if "volumen_hm3_anio" in tfilt.columns else None
            )
            if vol_col:
                top = tfilt.sort_values(vol_col, ascending=False).head(25)
                total_vol = float(pd.to_numeric(tfilt[vol_col], errors="coerce").fillna(0).sum())
                st.markdown(
                    scoreboard_html(
                        [
                            ("Títulos en filtro", f"{len(tfilt)}", "concesiones visibles"),
                            (
                                "Volumen autorizado",
                                f"{total_vol:,.0f}" + (" m³/año" if "m3" in vol_col else " hm³/año"),
                                "suma del filtro",
                            ),
                            ("Lectura", "Presión formal", "no es bombeo en vivo"),
                        ]
                    ),
                    unsafe_allow_html=True,
                )
            else:
                top = tfilt.head(25)
            repda_tbl = pd.DataFrame(
                {
                    "Título": top.get("titulo"),
                    "Colonia": top.get("colonia"),
                    "Alcaldía": top.get("alcaldia"),
                    "Uso": top.get("uso"),
                    "Volumen autorizado (m³/año)": top.get("volumen_m3_anio"),
                    "Titular": top.get("titular"),
                }
            )
            st.dataframe(
                paint_priority_table(repda_tbl),
                use_container_width=True,
                hide_index=True,
                height=360,
            )
        else:
            st.write("Sin títulos para este filtro.")

    with tab_piperos:
        st.markdown(
            section_banner(
                "Módulo piperos · decisión de carga en 10 segundos",
                "Izquierda = dónde sí cargar · Derecha = dónde evitar. Semáforo = estrés del pozo, no llenado de pipa.",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            explain_box(
                "<b>Guión de venta / operación:</b> "
                "1) elige un pozo <b>verde</b> cercano a tu ruta · "
                "2) si solo hay <b>ámbar</b>, úsalo con precaución · "
                "3) evita <b>rojo</b> salvo que no exista alternativa · "
                "4) pulsa <b>Enfocar</b> para verlo en el mapa."
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="z-legend">'
            '<span class="z-chip ok">Verde · cargar aquí</span>'
            '<span class="z-chip warn">Ámbar · precaución</span>'
            '<span class="z-chip bad">Rojo · evitar</span>'
            '<span class="z-chip info">No es nivel de tanque en vivo</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        preferir = (
            pie_series[pie_series["nivel_estres"].isin(["RECUPERACION_O_ESTABLE", "LEVE"])]
            .sort_values("tasa_abatimiento_m_anio")
            if len(pie_series)
            else pie.head(0)
        )
        precaucion = (
            pie_series[pie_series["nivel_estres"] == "MEDIO"]
            .sort_values("tasa_abatimiento_m_anio")
            if len(pie_series)
            else pie.head(0)
        )
        evitar = (
            pie_series[pie_series["nivel_estres"] == "ALTO"]
            .sort_values("tasa_abatimiento_m_anio", ascending=False)
            if len(pie_series)
            else pie.head(0)
        )
        st.markdown(
            scoreboard_html(
                [
                    ("Preferibles", f"{len(preferir)}", "verde · menor estrés"),
                    ("Precaución", f"{len(precaucion)}", "ámbar · usar con cuidado"),
                    ("Evitar", f"{len(evitar)}", "rojo · crítico"),
                ]
            ),
            unsafe_allow_html=True,
        )
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("##### Cargar aquí (menor estrés)")
            if len(preferir):
                cards = []
                for _, r in preferir.head(6).iterrows():
                    cards.append(
                        pipero_card_html(
                            f"Pozo {int(r['num_pozo'])} · {r.get('colonia', '')}",
                            f"{r.get('alcaldia', '')} · {r.get('semaforo', '')} · "
                            f"bajada {float(r.get('tasa_abatimiento_m_anio', 0) or 0):.2f} m/año · "
                            f"{r.get('consejo_para_piperos', '')}",
                            "ok",
                        )
                    )
                st.markdown("".join(cards), unsafe_allow_html=True)
                best = preferir.iloc[0]
                if st.button(f"Enfocar pozo preferible {int(best['num_pozo'])}", key="btn_best"):
                    st.session_state.pozo_sel = int(best["num_pozo"])
                    st.rerun()
            else:
                st.write("No hay pozos preferibles en este filtro.")
            if len(precaucion):
                st.markdown("##### Precaución (ámbar)")
                cards = []
                for _, r in precaucion.head(4).iterrows():
                    cards.append(
                        pipero_card_html(
                            f"Pozo {int(r['num_pozo'])} · {r.get('colonia', '')}",
                            f"{r.get('alcaldia', '')} · {r.get('semaforo', '')} · "
                            f"bajada {float(r.get('tasa_abatimiento_m_anio', 0) or 0):.2f} m/año · "
                            f"{r.get('consejo_para_piperos', '')}",
                            "warn",
                        )
                    )
                st.markdown("".join(cards), unsafe_allow_html=True)
        with col_b:
            st.markdown("##### Evitar si hay alternativa")
            if len(evitar):
                cards = []
                for _, r in evitar.head(6).iterrows():
                    cards.append(
                        pipero_card_html(
                            f"Pozo {int(r['num_pozo'])} · {r.get('colonia', '')}",
                            f"{r.get('alcaldia', '')} · {r.get('semaforo', '')} · "
                            f"bajada {float(r.get('tasa_abatimiento_m_anio', 0) or 0):.2f} m/año · "
                            f"{r.get('consejo_para_piperos', '')}",
                            "bad",
                        )
                    )
                st.markdown("".join(cards), unsafe_allow_html=True)
                worst = evitar.iloc[0]
                if st.button(f"Enfocar pozo crítico {int(worst['num_pozo'])}", key="btn_worst"):
                    st.session_state.pozo_sel = int(worst["num_pozo"])
                    st.rerun()
            else:
                st.write("No hay pozos críticos en este filtro.")

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
