-- Pegar en Supabase → SQL Editor → New query → Run
-- Activa mapas (PostGIS) y crea el esquema ZASEVA

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS zaseva;

-- Acuíferos (oferta)
CREATE TABLE IF NOT EXISTS zaseva.dim_acuifero (
  cve_acui text PRIMARY KEY,
  nom_acui text,
  nom_edo text,
  recarga_to_hm3 double precision,
  descarga_n_hm3 double precision,
  dma_negati_hm3 double precision,
  deficit_hm3 double precision,
  geom geometry(MultiPolygon, 4326)
);

-- Piezometría (proxy de sobreextracción)
CREATE TABLE IF NOT EXISTS zaseva.fact_pozo_piezometrico (
  num_pozo integer PRIMARY KEY,
  nom_pozo text,
  cve_acui text,
  nom_acuif text,
  latitud double precision,
  longitud double precision,
  tasa_abatimiento_m_anio double precision,
  delta_pne_m double precision,
  pne_ultimo_m double precision,
  n_obs integer,
  nivel_estres text,
  en_bbox_piloto boolean,
  peso_heatmap double precision,
  geom geometry(Point, 4326)
);

-- REPDA (concesiones)
CREATE TABLE IF NOT EXISTS zaseva.fact_repda_subtitulo (
  titulo text,
  titular text,
  uso text,
  volumen_m3_anio double precision,
  volumen_hm3_anio double precision,
  volumen_punto_m3_anio double precision,
  volumen_punto_hm3_anio double precision,
  fecha_titulo text,
  latitud double precision,
  longitud double precision,
  cve_acui text,
  nom_acui text,
  en_bbox_piloto boolean,
  geom geometry(Point, 4326)
);

CREATE TABLE IF NOT EXISTS zaseva.dim_municipio_piloto (
  cve_geo text PRIMARY KEY,
  nombre_mun text,
  entidad text,
  sps text,
  msm text,
  ahorro_uso_eficiente text,
  con_cuenca text,
  org_cuenca text,
  fecha_corte text
);

-- Vistas que lee Streamlit
CREATE OR REPLACE VIEW zaseva.v_oferta_acuifero AS
SELECT cve_acui, nom_acui, nom_edo, recarga_to_hm3, descarga_n_hm3,
       dma_negati_hm3, deficit_hm3
FROM zaseva.dim_acuifero;

CREATE OR REPLACE VIEW zaseva.v_heatmap_piezometria AS
SELECT num_pozo, nom_pozo, cve_acui, nom_acuif, latitud, longitud,
       tasa_abatimiento_m_anio, delta_pne_m, pne_ultimo_m, n_obs,
       nivel_estres, en_bbox_piloto, peso_heatmap
FROM zaseva.fact_pozo_piezometrico
WHERE n_obs >= 2 AND tasa_abatimiento_m_anio IS NOT NULL;

CREATE OR REPLACE VIEW zaseva.v_repda_poniente AS
SELECT titulo, titular, uso, volumen_m3_anio, volumen_hm3_anio,
       volumen_punto_m3_anio, volumen_punto_hm3_anio,
       latitud, longitud, cve_acui, nom_acui, en_bbox_piloto
FROM zaseva.fact_repda_subtitulo;
