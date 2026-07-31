# Pasos simples ZASEVA (GitHub + Supabase + Streamlit)

## Ya tienes
- Cuenta GitHub (edu@zaseva.com)
- Cuenta Streamlit
- Proyecto nuevo en Supabase

## Paso 1 — Supabase (activar mapas / PostGIS)
1. Entra a tu proyecto en https://supabase.com
2. Menú izquierdo: **SQL Editor**
3. **New query**
4. Copia TODO el archivo `sql/supabase_setup.sql` y pégalo
5. Click **Run**
6. Si dice success, PostGIS y las tablas ZASEVA ya existen

## Paso 2 — Anota la “llave” de la base (sin compartirla en chats públicos)
1. En Supabase: **Project Settings** → **Database**
2. Busca **Connection string** → URI
3. Copia algo como:
   postgresql://postgres:[YOUR-PASSWORD]@db.xxxxx.supabase.co:5432/postgres
4. Sustituye [YOUR-PASSWORD] por la contraseña del proyecto
5. Guárdala en un lugar privado (1Password / nota segura)

## Paso 3 — Sube este código a GitHub
1. En GitHub: **New repository**
   - Nombre sugerido: `zaseva-inteligencia-hidrica`
   - Private (recomendado)
2. Sube la carpeta `streamlit_app` como contenido del repo
   (desde la web: Add file → Upload files, o con GitHub Desktop)
3. Asegúrate de que en el repo se vean:
   - app.py
   - requirements.txt
   - data/
   - sql/
   - scripts/

## Paso 4 — Publica el dashboard en Streamlit
1. Entra a https://share.streamlit.io (o streamlit.io → Cloud)
2. **New app** / Create app
3. Conecta tu GitHub y elige el repo `zaseva-inteligencia-hidrica`
4. Main file path: `app.py`
5. Deploy
6. Cuando abra, verás el dashboard con los CSV (aunque aún no esté Supabase conectado)

## Paso 5 — Conectar Streamlit ↔ Supabase (opcional pero recomendado)
1. En la app de Streamlit Cloud: **Settings → Secrets**
2. Pega:
   SUPABASE_DB_URL = "postgresql://postgres:TU_PASSWORD@db.TU_PROYECTO.supabase.co:5432/postgres"
3. Save (la app se reinicia)

## Paso 6 — Cargar los datos a Supabase
En una computadora con Python (o pidiéndome a mí cuando tengas el repo conectado):

```bash
cd streamlit_app
pip install -r requirements.txt
export SUPABASE_DB_URL='postgresql://postgres:TU_PASSWORD@db.XXX.supabase.co:5432/postgres'
python scripts/load_to_supabase.py
```

Luego recarga la app Streamlit: debería leer la base (no solo CSV).

## Qué NO hagas
- No subas passwords a GitHub
- No descargues instaladores raros de postgis.net
- No pegues tu password de Supabase en chats públicos

## Resultado esperado
Una URL tipo:
https://zaseva-inteligencia-hidrica.streamlit.app
con el mapa del Corredor Poniente + KPIs.
