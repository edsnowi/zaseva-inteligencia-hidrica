-- =============================================================================
-- ZASEVA — Esquema espacial PostGIS (Corredor Poniente / CDMX–Edomex)
-- SRID 4326 · schema zaseva
--
-- Extiende sql/supabase_setup.sql con capas SAR (Sentinel-1), social listening
-- y score de severidad de fuga para el Dashboard B2G.
--
-- Uso (Supabase → SQL Editor, o psql):
--   \i sql/schema_geoespacial.sql
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS zaseva;

-- -----------------------------------------------------------------------------
-- AOI piloto Corredor Poniente (bbox usado por el ETL SAR)
-- SW: [-99.3100, 19.3000]  NE: [-99.1500, 19.4500]
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zaseva.dim_aoi_piloto (
    aoi_id          text PRIMARY KEY,
    nombre          text NOT NULL,
    alcaldias       text,
    geom            geometry(Polygon, 4326) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

INSERT INTO zaseva.dim_aoi_piloto (aoi_id, nombre, alcaldias, geom)
VALUES (
    'poniente_v1',
    'Corredor Poniente',
    'Cuajimalpa · Álvaro Obregón · Huixquilucan',
    ST_SetSRID(
        ST_MakeEnvelope(-99.3100, 19.3000, -99.1500, 19.4500),
        4326
    )
)
ON CONFLICT (aoi_id) DO UPDATE
SET nombre = EXCLUDED.nombre,
    alcaldias = EXCLUDED.alcaldias,
    geom = EXCLUDED.geom;

-- -----------------------------------------------------------------------------
-- 1) acuiferos_conagua — polígonos CONAGUA + DMA / déficit / recarga
--    Complementa zaseva.dim_acuifero (mismo dominio; esta tabla es la canónica
--    para el pipeline SAR + score de fuga).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zaseva.acuiferos_conagua (
    cve_acui            text PRIMARY KEY,
    nom_acui            text NOT NULL,
    nom_edo             text,
    recarga_hm3         double precision,   -- RECARGA_TO (hm³/año)
    descarga_natural_hm3 double precision,  -- DESCARGA_N
    dma_hm3             double precision,   -- DMA (negativo = déficit)
    deficit_hm3         double precision,   -- abs(DMA) cuando DMA < 0
    fuente              text DEFAULT 'CONAGUA-DMA',
    fecha_corte         date,
    geom                geometry(MultiPolygon, 4326) NOT NULL,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_acuiferos_conagua_geom
    ON zaseva.acuiferos_conagua USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_acuiferos_conagua_deficit
    ON zaseva.acuiferos_conagua (deficit_hm3 DESC NULLS LAST);

-- -----------------------------------------------------------------------------
-- 2) pozos_piezometricos — puntos REPDA/CONAGUA + PNE + volumen concesionado
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zaseva.pozos_piezometricos (
    pozo_id                 bigserial PRIMARY KEY,
    num_pozo                integer,
    nom_pozo                text,
    titulo_repda            text,
    titular                 text,
    uso                     text,
    cve_acui                text REFERENCES zaseva.acuiferos_conagua (cve_acui),
    nom_acui                text,
    latitud                 double precision NOT NULL,
    longitud                double precision NOT NULL,
    pne_ultimo_m            double precision,          -- profundidad nivel estático
    tasa_abatimiento_m_anio double precision,
    delta_pne_m             double precision,
    nivel_estres            text,                      -- ALTO | MEDIO | LEVE | ...
    volumen_concesionado_m3_anio double precision,     -- REPDA autorizado
    en_bbox_piloto          boolean DEFAULT false,
    fuente                  text DEFAULT 'CONAGUA-PIEZO/REPDA',
    geom                    geometry(Point, 4326) NOT NULL,
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_pozos_num_pozo UNIQUE (num_pozo)
);

CREATE INDEX IF NOT EXISTS idx_pozos_piezo_geom
    ON zaseva.pozos_piezometricos USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_pozos_piezo_estres
    ON zaseva.pozos_piezometricos (nivel_estres);

CREATE INDEX IF NOT EXISTS idx_pozos_piezo_acui
    ON zaseva.pozos_piezometricos (cve_acui);

-- -----------------------------------------------------------------------------
-- Capa auxiliar: zonas de hundimiento / grietas (InSAR o cartografía local)
-- Usada por el score de severidad cuando exista cobertura.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zaseva.zonas_subsidencia (
    zona_id             bigserial PRIMARY KEY,
    nombre              text,
    tasa_hundimiento_mm_anio double precision,
    severidad           text,              -- ALTA | MEDIA | BAJA
    fuente              text,
    geom                geometry(MultiPolygon, 4326) NOT NULL,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_zonas_subsidencia_geom
    ON zaseva.zonas_subsidencia USING GIST (geom);

-- -----------------------------------------------------------------------------
-- Colonias / alcaldías (agregación dashboard B2G)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zaseva.dim_colonia (
    id_colonia          text PRIMARY KEY,
    colonia             text NOT NULL,
    alcaldia            text NOT NULL,
    entidad             text DEFAULT 'CDMX',
    en_poniente         boolean DEFAULT false,
    poblacion           double precision,
    latitud_centro      double precision,
    longitud_centro     double precision,
    geom                geometry(MultiPolygon, 4326),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dim_colonia_geom
    ON zaseva.dim_colonia USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_dim_colonia_alcaldia
    ON zaseva.dim_colonia (alcaldia);

-- -----------------------------------------------------------------------------
-- 3) anomalias_satelitales_sar — píxeles/puntos Sentinel-1 (VV/VH dB)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zaseva.anomalias_satelitales_sar (
    anomalia_id         bigserial PRIMARY KEY,
    run_id              uuid NOT NULL,
    fecha_escena        date NOT NULL,
    fecha_inicio_ventana date NOT NULL,
    fecha_fin_ventana   date NOT NULL,
    polarizacion        text NOT NULL CHECK (polarizacion IN ('VV', 'VH', 'VV_VH')),
    backscatter_db      double precision NOT NULL,
    backscatter_db_baseline double precision,
    delta_db            double precision,          -- vs baseline / mediana local
    humedad_anomala     boolean NOT NULL DEFAULT false,
    speckle_filtrado    boolean NOT NULL DEFAULT true,
    cve_acui            text REFERENCES zaseva.acuiferos_conagua (cve_acui),
    pozo_critico_id     bigint REFERENCES zaseva.pozos_piezometricos (pozo_id),
    dist_pozo_critico_m double precision,
    latitud             double precision NOT NULL,
    longitud            double precision NOT NULL,
    geom                geometry(Point, 4326) NOT NULL,
    props               jsonb DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_anomalias_sar_geom
    ON zaseva.anomalias_satelitales_sar USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_anomalias_sar_run
    ON zaseva.anomalias_satelitales_sar (run_id);

CREATE INDEX IF NOT EXISTS idx_anomalias_sar_fecha
    ON zaseva.anomalias_satelitales_sar (fecha_escena DESC);

CREATE INDEX IF NOT EXISTS idx_anomalias_sar_humedad
    ON zaseva.anomalias_satelitales_sar (humedad_anomala)
    WHERE humedad_anomala = true;

-- -----------------------------------------------------------------------------
-- 4) reportes_social_listening — quejas ciudadanas georreferenciadas
--    (SUAC / X / medios / formularios ZASEVA)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zaseva.reportes_social_listening (
    reporte_id          bigserial PRIMARY KEY,
    fuente              text NOT NULL,             -- SUAC | X | FORM | OTRO
    tipo_evento         text,                      -- fuga | falta_agua | hundimiento | grieta
    descripcion         text,
    alcaldia            text,
    colonia             text,
    severidad_reportada smallint CHECK (severidad_reportada BETWEEN 0 AND 100),
    fecha_evento        timestamptz,
    url_origen          text,
    latitud             double precision,
    longitud            double precision,
    geom                geometry(Point, 4326),
    raw                 jsonb DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reportes_social_geom
    ON zaseva.reportes_social_listening USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_reportes_social_fecha
    ON zaseva.reportes_social_listening (fecha_evento DESC);

CREATE INDEX IF NOT EXISTS idx_reportes_social_alcaldia
    ON zaseva.reportes_social_listening (alcaldia);

-- -----------------------------------------------------------------------------
-- 5) mapa_salud_red_correlacionado — score 0–100 de severidad de fuga
--    Cruza SAR (humedad anómala) + subsidencia + abatimiento de pozos.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zaseva.mapa_salud_red_correlacionado (
    celda_id            bigserial PRIMARY KEY,
    run_id              uuid NOT NULL,
    fecha_calculo       date NOT NULL DEFAULT CURRENT_DATE,
    id_colonia          text REFERENCES zaseva.dim_colonia (id_colonia),
    colonia             text,
    alcaldia            text,
    cve_acui            text REFERENCES zaseva.acuiferos_conagua (cve_acui),
    -- Componentes del score (0–100 cada uno, antes de ponderar)
    score_sar_humedad   double precision NOT NULL DEFAULT 0,
    score_subsidencia   double precision NOT NULL DEFAULT 0,
    score_abatimiento   double precision NOT NULL DEFAULT 0,
    score_deficit_acui  double precision NOT NULL DEFAULT 0,
    score_social        double precision NOT NULL DEFAULT 0,
    -- Score final ponderado
    score_severidad_fuga double precision NOT NULL
        CHECK (score_severidad_fuga >= 0 AND score_severidad_fuga <= 100),
    nivel_riesgo_red    text GENERATED ALWAYS AS (
        CASE
            WHEN score_severidad_fuga >= 75 THEN 'CRITICO'
            WHEN score_severidad_fuga >= 50 THEN 'ALTO'
            WHEN score_severidad_fuga >= 25 THEN 'MEDIO'
            ELSE 'BAJO'
        END
    ) STORED,
    n_anomalias_sar     integer NOT NULL DEFAULT 0,
    n_pozos_criticos    integer NOT NULL DEFAULT 0,
    n_reportes_social   integer NOT NULL DEFAULT 0,
    deficit_acui_hm3    double precision,
    latitud             double precision NOT NULL,
    longitud            double precision NOT NULL,
    geom                geometry(Point, 4326) NOT NULL,
    detalle             jsonb DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mapa_salud_geom
    ON zaseva.mapa_salud_red_correlacionado USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_mapa_salud_score
    ON zaseva.mapa_salud_red_correlacionado (score_severidad_fuga DESC);

CREATE INDEX IF NOT EXISTS idx_mapa_salud_alcaldia
    ON zaseva.mapa_salud_red_correlacionado (alcaldia);

CREATE INDEX IF NOT EXISTS idx_mapa_salud_run
    ON zaseva.mapa_salud_red_correlacionado (run_id);

-- -----------------------------------------------------------------------------
-- 6) vista_diagnostico_alcaldia — agregados para Streamlit / Looker / Mapbox
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW zaseva.vista_diagnostico_alcaldia AS
WITH sar_criticos AS (
    SELECT
        c.alcaldia,
        c.colonia,
        c.id_colonia,
        COUNT(*) FILTER (WHERE a.humedad_anomala) AS puntos_fugas_invisibles
    FROM zaseva.dim_colonia c
    LEFT JOIN zaseva.anomalias_satelitales_sar a
        ON c.geom IS NOT NULL
       AND ST_Intersects(c.geom, a.geom)
    GROUP BY c.alcaldia, c.colonia, c.id_colonia
),
salud AS (
    SELECT
        alcaldia,
        colonia,
        id_colonia,
        AVG(score_severidad_fuga) AS score_severidad_promedio,
        MAX(score_severidad_fuga) AS score_severidad_max,
        MAX(nivel_riesgo_red) AS nivel_riesgo_red,  -- ver CASE abajo (no usar este MAX como semáforo)
        AVG(deficit_acui_hm3) AS deficit_acuifero_hm3,
        SUM(n_anomalias_sar) AS n_anomalias_sar,
        SUM(n_pozos_criticos) AS n_pozos_criticos,
        SUM(n_reportes_social) AS n_reportes_social
    FROM zaseva.mapa_salud_red_correlacionado
    GROUP BY alcaldia, colonia, id_colonia
),
riesgo_norm AS (
    SELECT
        s.*,
        CASE
            WHEN s.score_severidad_max >= 75 THEN 'CRITICO'
            WHEN s.score_severidad_max >= 50 THEN 'ALTO'
            WHEN s.score_severidad_max >= 25 THEN 'MEDIO'
            ELSE 'BAJO'
        END AS nivel_riesgo_estructural
    FROM salud s
)
SELECT
    COALESCE(r.alcaldia, sc.alcaldia) AS alcaldia,
    COALESCE(r.colonia, sc.colonia) AS colonia,
    COALESCE(r.id_colonia, sc.id_colonia) AS id_colonia,
    COALESCE(sc.puntos_fugas_invisibles, 0) AS conteo_puntos_criticos_fugas,
    COALESCE(r.deficit_acuifero_hm3, 0) AS deficit_acuifero_hm3,
    COALESCE(r.score_severidad_promedio, 0) AS score_severidad_promedio,
    COALESCE(r.score_severidad_max, 0) AS score_severidad_max,
    COALESCE(r.nivel_riesgo_estructural, 'BAJO') AS nivel_riesgo_estructural,
    COALESCE(r.n_pozos_criticos, 0) AS n_pozos_criticos,
    COALESCE(r.n_reportes_social, 0) AS n_reportes_social
FROM riesgo_norm r
FULL OUTER JOIN sar_criticos sc
    ON r.id_colonia = sc.id_colonia;

-- Resumen por alcaldía (capa ejecutiva B2G)
CREATE OR REPLACE VIEW zaseva.vista_diagnostico_alcaldia_resumen AS
SELECT
    alcaldia,
    SUM(conteo_puntos_criticos_fugas) AS puntos_criticos_fugas,
    AVG(deficit_acuifero_hm3) AS deficit_acuifero_hm3_promedio,
    AVG(score_severidad_promedio) AS score_severidad_promedio,
    MAX(score_severidad_max) AS score_severidad_max,
    CASE
        WHEN MAX(score_severidad_max) >= 75 THEN 'CRITICO'
        WHEN MAX(score_severidad_max) >= 50 THEN 'ALTO'
        WHEN MAX(score_severidad_max) >= 25 THEN 'MEDIO'
        ELSE 'BAJO'
    END AS nivel_riesgo_estructural,
    COUNT(*) AS n_colonias
FROM zaseva.vista_diagnostico_alcaldia
WHERE alcaldia IS NOT NULL
GROUP BY alcaldia
ORDER BY score_severidad_max DESC NULLS LAST;

COMMENT ON TABLE zaseva.acuiferos_conagua IS
    'Polígonos de acuíferos CONAGUA con DMA, déficit y recarga (hm³/año).';
COMMENT ON TABLE zaseva.pozos_piezometricos IS
    'Pozos piezométricos / REPDA: PNE, abatimiento y volumen concesionado.';
COMMENT ON TABLE zaseva.anomalias_satelitales_sar IS
    'Anomalías Sentinel-1 (VV/VH dB) post Speckle Filter, humedad dieléctrica anómala.';
COMMENT ON TABLE zaseva.reportes_social_listening IS
    'Eventos de quejas ciudadanas georreferenciados (SUAC / redes / formularios).';
COMMENT ON TABLE zaseva.mapa_salud_red_correlacionado IS
    'Cruce SAR × subsidencia × pozos → Score de Severidad de Fuga (0–100).';
COMMENT ON VIEW zaseva.vista_diagnostico_alcaldia IS
    'Agregado por colonia/alcaldía para Dashboard B2G (Streamlit / Looker / Mapbox).';
