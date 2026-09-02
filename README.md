# Monitor de Proyectos Mineros · Chile

Sistema que **cada lunes** busca automáticamente información sobre proyectos
mineros en Chile y la publica en un **dashboard web** que tu equipo abre desde
una URL. No requiere servidor propio ni pago: funciona sobre GitHub (Actions +
Pages), ambos gratuitos.

## Cómo funciona

```
  Lunes 08:00  ──►  GitHub Actions ejecuta collector.py
                         │
                         ├─ e-SEIA  (proyectos oficiales que entran a evaluación)
                         ├─ Google News RSS (noticias de prensa)
                         └─ Claude API + web_search (oportunidades para Recursos y Reservas)
                         │
                         ▼
                    docs/data/latest.json   (se guarda en el repo)
                         │
                         ▼
             GitHub Pages sirve docs/index.html  ──►  tu equipo abre la URL
```

- **collector.py** — recolecta y guarda los datos en `docs/data/`.
- **docs/index.html** — dashboard estático (filtros por región, tipo, búsqueda).
- **.github/workflows/weekly.yml** — el programador semanal.

La sección "Oportunidades para Recursos y Reservas" es la única parte de pago del
sistema: usa la API de Claude con búsqueda web para curar, cada semana, noticias e
hitos que representen una oportunidad comercial concreta para el área de R&R de SRK
(no solo exploración greenfield — también auditorías de recursos, planificación minera,
CAPEX de infraestructura, etc., según el enfoque de negocio real). Ver "Puesta en
marcha" y "Nota sobre costos" más abajo.

## Puesta en marcha (una sola vez, ~10 min)

1. **Crea un repositorio** en GitHub (público o privado) y sube estos archivos.
2. Ve a **Settings → Pages** y en "Source" elige la rama `main` y la carpeta
   **`/docs`**. Guarda. GitHub te dará una URL tipo
   `https://TU-USUARIO.github.io/TU-REPO/` — ésa es la del dashboard.
3. Ve a **Settings → Actions → General → Workflow permissions** y activa
   **"Read and write permissions"** (para que el bot pueda guardar los datos).
4. Ve a **Settings → Secrets and variables → Actions → New repository secret** y crea
   `ANTHROPIC_API_KEY` con tu API key de Anthropic. Sin este secret el dashboard sigue
   funcionando igual, solo que sin la sección "Oportunidades para Recursos y Reservas".
5. (Opcional) En la pestaña **Actions** abre el workflow y pulsa **"Run workflow"**
   para lanzarlo de inmediato y no esperar al lunes.

Listo. Desde ahí corre solo cada lunes y el dashboard se actualiza.

### Acceso del equipo
- Repo **público** → cualquiera con la URL ve el dashboard, y además GitHub Pages y las
  horas de GitHub Actions son gratis sin límite práctico. **Es la opción recomendada
  para minimizar costo**, dado que los datos en sí (e-SEIA y prensa son públicos, y las
  oportunidades se arman a partir de fuentes públicas) no son confidenciales.
- Repo **privado** → pierde ambas gratuidades: GitHub Pages privado requiere un plan de
  pago (Team/Enterprise), y las horas de Actions dejan de ser ilimitadas. Si de todos
  modos se necesita privado, la alternativa es desplegar `docs/` en algo como
  Netlify/Vercel con acceso restringido.

### Nota sobre costos

Todo el sistema es gratuito salvo la sección de "Oportunidades para Recursos y Reservas"
(usa la API de Claude, que es de pago). Ya está configurada con las opciones más
económicas disponibles para minimizar ese costo:

- Modelo `claude-sonnet-5` (no `claude-opus-5`, que es más caro).
- `output_config.effort: "medium"` — la primera corrida real con `"low"` no encontró
  ninguna oportunidad, así que se subió un nivel. Si vuelve a pasar, el siguiente ajuste
  es `max_uses` (más búsquedas) antes que subir a `"high"` o cambiar de modelo.
- Máximo 4 búsquedas web (`max_uses`) por corrida.
- Cadencia semanal, no diaria.

Aun así, cada corrida consume una cantidad de tokens que varía según cuánto necesite
investigar esa semana — revisa las tarifas vigentes en la consola de Anthropic antes de
dejarlo corriendo indefinidamente. Para bajar el costo: reduce `effort` de vuelta a
`"low"` o espacia el cron a cada dos semanas. Para subir la calidad de las oportunidades
detectadas: sube `max_uses`, y solo después `effort` a `"high"`.

## Probar en tu computador (opcional)

```bash
pip install -r requirements.txt

# sin internet ni API key, con datos de ejemplo (incluye oportunidades de muestra):
python collector.py --sample

# corrida real (consulta la red; para incluir oportunidades hace falta ANTHROPIC_API_KEY):
export ANTHROPIC_API_KEY=sk-ant-...     # PowerShell: $env:ANTHROPIC_API_KEY = "sk-ant-..."
python collector.py

# previsualizar el dashboard:
cd docs && python -m http.server 8000
# abre http://localhost:8000
```

Al correr con `ANTHROPIC_API_KEY` real, conviene revisar `docs/data/latest.json` y
confirmar que `oportunidades` trae los 7 campos esperados por ítem (`proyecto`,
`empresa`, `region`, `linea_servicio`, `relevancia`, `fuente_url`, `fecha`) antes de
dejarlo corriendo en el cron semanal.

## Ajustes frecuentes

- **Hora / día:** edita el `cron` en `.github/workflows/weekly.yml` (está en UTC; ver
  nota del archivo).
- **Qué se considera "minería":** lista `KEYWORDS_MINERIA` en `collector.py`.
- **Búsquedas de prensa:** lista `NEWS_QUERIES` en `collector.py`.
- **Solo sector minería en el SEIA:** fija `SEIA_SECTOR_ID` con el id del sector
  (lo ves en la URL del buscador avanzado al elegir "Minería").
- **Enfoque de las oportunidades para R&R:** edita `OPORTUNIDADES_PROMPT` (el texto de
  la investigación) y `OPORTUNIDADES_SCHEMA` (las líneas de servicio del enum
  `linea_servicio`) en `collector.py`.

## Nota importante sobre las fuentes

El e-SEIA es un sitio del Estado y puede cambiar sin aviso — de hecho ya cambió una vez:
originalmente `fetch_seia` parseaba una tabla HTML, pero el sitio migró a un endpoint
JSON (`buscarProyectoResumenAction.php`, un backend de DataTables), así que la función
ahora hace un POST directo a ese endpoint. **Conviene correr `python collector.py` una
vez de forma local** de vez en cuando para confirmar que sigue funcionando antes de
confiar ciegamente en la automatización. Si el sitio vuelve a cambiar su estructura, el
único lugar a ajustar es `fetch_seia` en `collector.py`.

Este panel es referencial. Para decisiones, verifica siempre en la fuente oficial
(https://seia.sea.gob.cl).
