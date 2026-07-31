# ZASEVA — Documento de negocio del dashboard
## Corredor Poniente (Cuajimalpa · Álvaro Obregón · Huixquilucan)

**Qué es este archivo:**  
Resumen en lenguaje de negocio de lo que muestra el Centro de Inteligencia Hídrica, qué significa para vender, y un glosario de términos/acrónimos.  
Sirve para el equipo comercial, partners e inversionistas (no es un manual técnico).

**App en vivo:**  
https://zaseva-inteligencia-hidrica-aspevioebqnbofqmji2the.streamlit.app/

**Repo:**  
https://github.com/edsnowi/zaseva-inteligencia-hidrica

---

## 1. La idea de ZASEVA (recordatorio)

ZASEVA opera como un **“Caballo de Troya”**:

1. **Frente comercial (lo que el cliente compra hoy):**  
   App simple B2C/B2B para que condominios, industrias y hogares pidan **agua potable en pipas**.

2. **Fondo de inteligencia (lo que construye ventaja):**  
   Cada operación (viajes, esperas, entregas, geocercas en pozos/garzas) se convierte en **sensor ambulante** del sistema hídrico.

El dashboard actual es la **primera capa de inteligencia con datos públicos** (CONAGUA / REPDA / piezometría / sequía), antes de tener aún el extracto completo de viajes ZASEVA.

---

## 2. Qué estás viendo en el dashboard

### 2.1 Déficit de acuíferos ≈ **609 hm³/año**
- Acuífero ZM Ciudad de México (clave **0901**): déficit ≈ **480** hm³/año  
- Acuífero Valle de Toluca (clave **1501**): déficit ≈ **129** hm³/año  

**Traducción de negocio:**  
El subsuelo de la zona metropolitana / poniente **ya opera en números rojos**: se extrae más agua de la que se recarga.  
Eso explica por qué condominios e industrias con cisternas grandes necesitan **suministro rodado recurrente**, no solo emergencias.

### 2.2 REPDA autorizado ≈ **25 hm³/año** (101 títulos / ~293 puntos)
Volumen de agua **concesionado legalmente** en el bbox del Corredor Poniente (no es automáticamente el bombeo real de cada día).

Usos líderes en el piloto (orden aproximado):  
Servicios → Público urbano → Industrial → Agrícola.

**Traducción de negocio:**  
Hay demanda/extracción formal concentrada (clubes, servicios, industria, organismos).  
Es un mapa de **quién tiene derecho a sacar agua** y con qué uso.

### 2.3 Pozos en estrés ALTO ≈ **35**
La red piezométrica muestra que el nivel del agua subterránea **baja** en el tiempo (el pozo se “hace más profundo”).

**Traducción de negocio:**  
No es solo un cálculo administrativo: hay **síntoma físico** de presión/sobreextracción.  
En el mapa, los focos más rojos/naranjas son zonas más tensionadas.

### 2.4 Sequía municipal: **SIN SEQUÍA** (corte ene-2026)
Cuajimalpa, Álvaro Obregón y Huixquilucan aparecen sin alerta de sequía en ese corte.

**Traducción de negocio (clave):**  
El problema del Corredor Poniente **no se reduce a “este mes no llovió”**.  
Es **estructural**: red de tubería vulnerable + acuífero deficitario + extracción alta.  
Eso fortalece la narrativa de contratos de suministro continuo.

### 2.5 El mapa
Combina:
- acuíferos en déficit,
- puntos donde baja el nivel freático,
- puntos de concesiones REPDA.

**Traducción de negocio:**  
Responde “**dónde duele el agua**” a escala de corredor, no solo el titular de “CDMX sin agua”.

---

## 3. Qué nos está diciendo esta data (la historia)

1. Hay **escasez real de oferta subterránea** (déficit DMA).  
2. Hay **extracción/autorización concentrada** (REPDA).  
3. Hay **evidencia de presión en campo** (piezómetros).  
4. El riesgo **no depende solo del clima de la semana** (sin sequía + déficit igual).  
5. Por tanto: el mercado de pipas en el Corredor Poniente es **recurrente y defendible**.

Esto valida el modelo:  
**vender agua (cashflow)** mientras se construye **inteligencia territorial (moat)**.

---

## 4. Qué se puede vender a partir de esto

| Producto | A quién | Qué compra el cliente |
|---|---|---|
| **Suministro de agua / contratos** | Administradores de condominios, industrias, hoteles | Continuidad de agua en zona de alto riesgo |
| **Radar de riesgo hídrico** | Property managers, family offices, desarrolladores | Semáforo/mapa de estrés por corredor o colonia |
| **Inteligencia operativa** | Flota ZASEVA / partners de pipas | Priorizar rutas, horarios y puntos de carga (cuando existan viajes) |
| **Informes B2B / ESG / gobierno** | Corporativos, municipios, fondos | Evidencia con fuentes oficiales (CONAGUA/REPDA) |
| **Scoring de sitios** | Real estate / developers | Evaluar riesgo de desabasto antes de invertir u operar |

### Lo que aún NO está completo (próxima capa)
Cuando exista telemetría de viajes ZASEVA:
- tiempos reales de espera en pozos/garzas,
- volumen movilizado día a día,
- saturación operativa,
- inferencia más fina de cortes por colonia.

---

## 5. Frase comercial lista para usar

> “En el Corredor Poniente el acuífero ya opera en déficit (~609 hm³/año), hay focos de abatimiento medidos y concesiones concentradas. Aunque el semáforo de sequía diga ‘sin sequía’, el riesgo de desabasto es estructural. ZASEVA asegura suministro y, con la operación, convierte cada viaje en inteligencia del territorio.”

---

## 6. Glosario de términos y acrónimos

### Negocio / producto
- **B2C:** venta a consumidor final (hogares).  
- **B2B:** venta a empresas / condominios / industrias.  
- **Caballo de Troya:** estrategia ZASEVA: producto comercial visible + motor de datos detrás.  
- **Dashboard / Centro de Inteligencia Hídrica:** pantalla donde se ven KPIs y mapas del agua.  
- **KPI:** indicador clave (ej. déficit, títulos REPDA, pozos en estrés).  
- **MVP:** versión mínima usable del producto (este dashboard ya lo es a nivel visual).  
- **Piloto / Corredor Poniente:** zona inicial CDMX–Edomex (Cuajimalpa, Álvaro Obregón, Huixquilucan).

### Agua / México
- **CONAGUA:** Comisión Nacional del Agua (autoridad federal del agua).  
- **DOF:** Diario Oficial de la Federación (donde se publican acuerdos, incl. disponibilidades).  
- **DMA (Disponibilidad Media Anual):** cuánta agua “sobra” o “falta” en un acuífero en promedio anual.  
  - **DMA negativa / déficit:** se usa más de lo sostenible.  
- **Acuífero:** “depósito” subterráneo de agua (aquí: 0901 ZMCDMX y 1501 Valle de Toluca).  
- **hm³ (hectómetro cúbico):** unidad de volumen grande. 1 hm³ = 1,000,000 m³ ≈ 1 mil millones de litros.  
- **Recarga:** agua que entra al acuífero (lluvia infiltrada, etc.).  
- **Extracción / bombeo:** agua que se saca por pozos.  
- **Cisterna:** almacenamiento en edificios/condominios (en el piloto, a menudo 50k–200k litros).  
- **Pipa / garza / pozo de carga:** camión cisterna y puntos donde se carga agua.  
- **Red pública / tubería:** red municipal; en zonas altas (>2,600 m) pierde presión primero ante recortes (ej. Cutzamala).  
- **Cutzamala:** sistema que aporta agua superficial a la zona metropolitana; sus recortes tensionan la red.  
- **Sequía municipal / SPS / MSM:** semáforos y monitor oficiales de sequía por municipio.  
- **INEGI:** instituto de estadísticas/geografía (densidad poblacional, etc.; capa futura de demanda).  
- **SUAC:** reportes ciudadanos de fallas/fugas/falta de agua en CDMX (capa futura de riesgo).

### Derechos / extracción legal
- **REPDA:** Registro Público de Derechos de Agua.  
  Lista de **títulos/concesiones**: quién puede usar agua, cuánto (autorizado) y para qué uso.  
- **Título / concesión:** permiso legal de aprovechamiento.  
- **Volumen autorizado:** lo permitido en el título (no siempre igual a lo bombeado realmente).

### Medición de estrés en campo
- **Piezómetro / red piezométrica:** pozos de observación del **nivel** del agua subterránea.  
- **PNE (profundidad del nivel estático):** qué tan “abajo” está el agua. Si sube con los años → el acuífero se abate.  
- **Abatimiento:** baja del nivel freático (síntoma de presión/sobreextracción).  
- **Sobreextracción:** sacar más agua de la que el sistema puede reponer de forma sostenible.

### Datos / tecnología (lo mínimo que debes conocer)
- **GIS:** mapas con datos (ubicaciones, áreas, rutas).  
- **PostGIS:** extensión de base de datos para guardar y consultar mapas.  
- **PostgreSQL / “Postgres”:** el tipo de base de datos; Supabase lo usa por debajo.  
- **Supabase:** servicio en la nube donde está el “archivero” de datos ZASEVA.  
- **Streamlit:** herramienta para publicar el dashboard como página web.  
- **GitHub:** lugar donde vive el código del dashboard.  
- **CSV:** archivo de tabla (Excel-friendly) usado como respaldo de datos.  
- **Shapefile (.shp):** formato clásico de mapa/geometría de CONAGUA.  
- **Secret / Secrets:** contraseñas guardadas en Streamlit (no van en el código público).  
- **URI / connection string:** “dirección + llave” para conectarse a la base de datos.  
- **Session pooler:** puerta de acceso recomendada a Supabase desde internet (la que usamos).  
- **Token de GitHub (PAT):** llave temporal para subir código; se revoca después de usarla.

---

## 7. Fuentes de datos usadas en este piloto

| Capa | Fuente | Rol en el negocio |
|---|---|---|
| Oferta / déficit de acuíferos | CONAGUA – Disponibilidad media anual (DMA) | Prueba de escasez estructural |
| Estrés local | CONAGUA – Red piezométrica | Prueba de abatimiento en campo |
| Extracción autorizada | REPDA (anexos subterráneos) | Mapa de concesiones y usos |
| Sequía oficial | Dataset municipal de sequía | Contraste clima vs estrés estructural |
| Operación ZASEVA | Aún pendiente (viajes/app) | Capa propietaria futura (ventaja competitiva) |

---

## 8. Próximos pasos sugeridos (negocio + datos)

1. Conectar Streamlit → Supabase (Secrets) para que la app lea la base oficial.  
2. Rotar/cambiar password de Supabase (se compartió durante el setup).  
3. Decidir visibilidad del repo GitHub (hoy público para facilitar Streamlit).  
4. Sumar capas de demanda (INEGI / colonias) y, cuando exista, telemetría de viajes ZASEVA.  
5. Empaquetar un **one-pager comercial** para condominios a partir de la sección 4 y 5 de este documento.

---

## 9. Nota de uso interno

Este documento refleja la conversación de diseño de datos/negocio del piloto Corredor Poniente.  
Los números pueden actualizarse cuando se recarguen datasets CONAGUA/REPDA o cuando entre la telemetría propia de ZASEVA.

*Última actualización de contenido: julio 2026.*
