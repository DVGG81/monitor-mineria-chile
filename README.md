# Monitor de Proyectos Mineros · Chile

Sistema que **cada lunes** busca automáticamente información sobre proyectos
mineros en Chile y genera un **dashboard** con los resultados. No requiere
servidor propio ni pago: funciona sobre GitHub Actions (gratuito).

## Cómo funciona

```
  Lunes 08:00  ──►  GitHub Actions ejecuta collector.py
                         │
                         ├─ e-SEIA  (proyectos oficiales que entran a evaluación)
                         ├─ Google News RSS (noticias de prensa)
                         └─ Claude API + web_search (oportunidades para Recursos y Reservas)
                         │
                         ▼
             docs/data/latest.json + docs/reporte.html   (se guardan en el repo)
                         │
                         ▼
     docs/reporte.html: descárgalo tú mismo desde github.com y ábrelo
             (o, si tu red permite *.github.io, GitHub Pages sirve docs/index.html)
```

- **collector.py** — recolecta los datos y genera tanto `docs/data/` como `docs/reporte.html`.
- **docs/index.html** — plantilla del dashboard; sirve tal cual vía GitHub Pages (carga los
  datos con `fetch`).
- **docs/reporte.html** — el mismo dashboard pero **autocontenido**: cada corrida incrusta
  los datos directamente en el archivo, así que se abre local con doble clic, sin depender
  de una URL ni de GitHub Pages. Pensado para cuando la política de red de la empresa
  bloquea `*.github.io` (caso común).
- **.github/workflows/weekly.yml** — el programador semanal.

### Cómo conseguir `docs/reporte.html` cada semana

1. Entra al repo en `github.com/TU-USUARIO/TU-REPO` (esto sí funciona aunque `*.github.io`
   esté bloqueado — son dominios distintos).
2. Abre `docs/reporte.html` en la vista de código.
3. Botón **"Download raw file"** (el ícono de descarga, arriba a la derecha del archivo) para
   guardarlo en tu computador.
4. Ábrelo con doble clic (se abre en tu navegador sin conexión a internet, salvo por las
   fuentes de Google Fonts que son puramente cosméticas) o súbelo a la carpeta de
   SharePoint/OneDrive que uses con tu equipo.

Alternativa si usas git: `git pull` en tu copia local y abre `docs/reporte.html` directo.

La sección "Oportunidades para Recursos y Reservas" es la única parte de pago del
sistema: usa la API de Claude con búsqueda web para curar, cada semana, noticias e
hitos que representen una oportunidad comercial concreta para el área de R&R de SRK
(no solo exploración greenfield — también auditorías de recursos, planificación minera,
CAPEX de infraestructura, etc., según el enfoque de negocio real). Ver "Puesta en
marcha" y "Nota sobre costos" más abajo.

## Puesta en marcha (una sola vez, ~10 min)

1. **Crea un repositorio** en GitHub (público o privado) y sube estos archivos.
2. Ve a **Settings → Actions → General → Workflow permissions** y activa
   **"Read and write permissions"** (para que el bot pueda guardar los datos).
3. Ve a **Settings → Secrets and variables → Actions → New repository secret** y crea
   `ANTHROPIC_API_KEY` con tu API key de Anthropic. Sin este secret el dashboard sigue
   funcionando igual, solo que sin la sección "Oportunidades para Recursos y Reservas".
4. (Opcional, solo si tu red no bloquea `*.github.io`) Ve a **Settings → Pages** y en
   "Source" elige la rama `main` y la carpeta **`/docs`**. GitHub te dará una URL tipo
   `https://TU-USUARIO.github.io/TU-REPO/` con el dashboard siempre actualizado. Si tu
   empresa bloquea ese dominio (como en SRK), sáltate este paso y usa
   `docs/reporte.html` — ver la sección de arriba.
5. En la pestaña **Actions** abre el workflow y pulsa **"Run workflow"** para lanzarlo
   de inmediato y no esperar al lunes.

Listo. Desde ahí corre solo cada lunes.

### Acceso del equipo
- Vía `docs/reporte.html`: descárgalo del repo cada semana (ver arriba) y compártelo por
  donde ya distribuyas archivos con tu equipo (SharePoint, OneDrive, correo). No depende
  de la visibilidad del repo.
- Vía GitHub Pages (si tu red lo permite): repo **público** → cualquiera con la URL ve el
  dashboard, y Pages + Actions son gratis sin límite práctico. Repo **privado** → pierde
  ambas gratuidades (Pages privado requiere plan de pago; Actions tiene minutos
  limitados).

### Nota sobre costos

Todo el sistema es gratuito salvo la sección de "Oportunidades para Recursos y Reservas"
(usa la API de Claude, que es de pago). Ya está configurada con las opciones más
económicas disponibles para minimizar ese costo:

- Modelo `claude-sonnet-5` (no `claude-opus-5`, que es más caro).
- `output_config.effort: "low"`.
- Máximo 3 búsquedas web (`max_uses`) por corrida.
- **Una sola llamada a la API, sin reintentos.** Se probó subir `effort` a `"medium"` con
  reintentos automáticos si el modelo no terminaba en un turno (`pause_turn`), y en la
  práctica una corrida tardó ~8 minutos y gastó bastante más de lo esperado — cada
  reintento es una llamada nueva de precio completo. Ahora, si no alcanza a terminar en
  un turno, simplemente no hay oportunidades esa semana en vez de insistir pagando más.
- Cadencia semanal, no diaria.

Aun así, cada corrida consume una cantidad de tokens que varía según cuánto necesite
investigar esa semana — revisa las tarifas vigentes en la consola de Anthropic antes de
dejarlo corriendo indefinidamente. Para subir la calidad de las oportunidades detectadas
sin arriesgar corridas largas/caras: sube primero `max_uses` de a poco (ej. a 4 o 5) y
mide cuánto tarda; solo después considera subir `effort`, y hazlo sabiendo que puede
alargar mucho la corrida si el modelo no termina en un turno.

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
