#!/usr/bin/env python3
"""
Recolector semanal de información sobre proyectos mineros en Chile.

Fuentes:
  1. e-SEIA (Servicio de Evaluación Ambiental): proyectos que ingresan al
     Sistema de Evaluación de Impacto Ambiental. Es el registro OFICIAL de
     nuevos proyectos de inversión, incluida la minería.
     Endpoint: https://seia.sea.gob.cl/busqueda/buscarProyectoAction.php
  2. Google News RSS: noticias de prensa que mencionan proyectos mineros.

El script produce:
  docs/data/latest.json   -> corrida más reciente (la que muestra el dashboard)
  docs/data/history.json  -> histórico acumulado (para ver evolución)

Uso:
  python collector.py            # corrida real (consulta la red)
  python collector.py --sample   # genera datos de MUESTRA sin red (para probar el dashboard)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Dependencias externas (ver requirements.txt). Se importan dentro de las
# funciones de red para que --sample funcione aunque no estén instaladas.

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "docs" / "data"

# Palabras clave para reconocer que un proyecto/noticia es de minería.
KEYWORDS_MINERIA = [
    "miner", "cobre", "litio", "oro", "plata", "molibdeno", "hierro",
    "cátodo", "concentrado", "faena", "relave", "yacimiento", "prospección",
    "sondaje", "planta de", "sulfuros", "óxidos", "codelco", "bhp", "escondida",
]

# Consultas de noticias para Google News RSS.
NEWS_QUERIES = [
    "proyecto minero Chile",
    "minería Chile inversión",
    "SEIA proyecto minero",
    "cobre litio proyecto Chile",
]

# Prompt de investigación para la sección "Oportunidades para Recursos y Reservas"
# (ver fetch_oportunidades_rr). Editar aquí para ajustar el enfoque de la búsqueda.
OPORTUNIDADES_PROMPT = """\
Eres un analista de inteligencia minera para el área de Recursos y Reservas de SRK \
Consulting Chile. Tu tarea es investigar y reportar, para la semana en curso, situaciones \
de negocio en la minería y exploración chilena que representen una oportunidad comercial \
concreta para SRK.

SRK Minería en Chile trabaja tanto con juniors explorers como con grandes operadores \
(Codelco, Minera Escondida/BHP, Kinross, South32, Antofagasta Minerals, Anglo American, \
Teck, Glencore, Lundin Mining, entre otros). Las líneas de servicio relevantes son:

1. Estimación o actualización de modelos de recursos y reservas (geología, variografía, \
   geometalurgia, NI 43-101/JORC o estándares chilenos equivalentes).
2. Auditoría o debida diligencia de modelos de recursos existentes — típica en procesos \
   de fusión, adquisición, venta de activos o cambio de operador.
3. Planificación minera de corto y largo plazo, y evaluación de escenarios estratégicos \
   (incluye análisis estocástico de reservas o producción).
4. Ingeniería conceptual de minería subterránea profunda y selección de métodos de \
   explotación (block/panel caving, layouts).
5. Estimación de CAPEX de infraestructura minera.
6. Exploración y permisos de proyectos nuevos: sondajes, primeras estimaciones de \
   recursos, permisos SERNAGEOMIN, financiamiento de juniors (TSX-V, ASX, etc.).

Busca noticias e hitos de las últimas dos semanas que calcen con una o más de estas \
líneas: resultados de sondajes, nuevas o actualizadas estimaciones de recursos, procesos \
de M&A o due diligence en activos mineros chilenos, anuncios de estudios de factibilidad \
o ingeniería (conceptual, básica, de detalle), expansión o cambios de infraestructura \
minera, cambios de operador o financiamiento en proyectos de exploración, permisos de \
exploración aprobados por SERNAGEOMIN, y anuncios de junior explorers sobre proyectos \
chilenos. Usa la herramienta de búsqueda web para cubrir fuentes como SERNAGEOMIN, \
COCHILCO, mining.com, Minería Chilena, comunicados de prensa de empresas (junior y \
grandes operadores), y bolsas de valores relevantes.

No dupliques el registro genérico del e-SEIA (ya cubierto por otra fuente): concéntrate \
en la señal de negocio -por qué esto genera trabajo para SRK-, no en el ingreso \
administrativo del proyecto. Si no hay suficientes novedades recientes y relevantes, \
devuelve una lista más corta o vacía en vez de rellenar con proyectos antiguos o poco \
relevantes.

Para cada oportunidad entrega: nombre del proyecto u operación, empresa/titular, región \
de Chile (o "Nacional" si no aplica), la línea de servicio SRK más relevante, una \
explicación breve y concreta de por qué es relevante, la fecha de la noticia o hito, y la \
URL de la fuente. Responde únicamente con la lista de oportunidades en el formato \
solicitado.
"""

# Schema de salida estructurada para fetch_oportunidades_rr (output_config.format).
OPORTUNIDADES_SCHEMA = {
    "type": "object",
    "properties": {
        "oportunidades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "proyecto": {"type": "string"},
                    "empresa": {"type": "string"},
                    "region": {"type": "string"},
                    "linea_servicio": {
                        "type": "string",
                        "enum": [
                            "Recursos y reservas (estimación/actualización)",
                            "Auditoría / debida diligencia de recursos",
                            "Planificación minera y escenarios estratégicos",
                            "Minería subterránea / métodos de explotación",
                            "CAPEX / infraestructura minera",
                            "Exploración y permisos (proyecto nuevo)",
                            "Otra",
                        ],
                    },
                    "relevancia": {"type": "string"},
                    "fuente_url": {"type": "string"},
                    "fecha": {"type": "string"},
                },
                "required": ["proyecto", "empresa", "region", "linea_servicio",
                             "relevancia", "fuente_url", "fecha"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["oportunidades"],
    "additionalProperties": False,
}

# e-SEIA: parámetros del buscador. El endpoint acepta GET.
SEIA_URL = "https://seia.sea.gob.cl/busqueda/buscarProyectoAction.php"
# Cuántas páginas de resultados recientes revisar (10 proyectos por página aprox).
SEIA_MAX_PAGINAS = 5
# Nota: el buscador permite filtrar por "sector productivo = Minería" con un id
# numérico en el parámetro `sector`. Si conoces ese id lo puedes fijar aquí para
# consultar solo minería. Si lo dejas en None, el script trae los proyectos más
# recientes de todos los sectores y filtra por palabra clave (más robusto ante
# cambios del sitio). Para hallar el id: abre el buscador, elige "Minería" y mira
# el parámetro en la URL o en el formulario.
SEIA_SECTOR_ID = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MonitorMineriaCL/1.0; monitoreo interno de "
        "proyectos mineros)"
    )
}


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def es_mineria(texto: str) -> bool:
    t = (texto or "").lower()
    return any(k in t for k in KEYWORDS_MINERIA)


def limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "")).strip()


# --------------------------------------------------------------------------
# Fuente 1: e-SEIA
# --------------------------------------------------------------------------

def fetch_seia() -> list[dict]:
    """Consulta el buscador del e-SEIA y devuelve proyectos mineros recientes.

    Parsea la tabla HTML de resultados de forma defensiva: localiza la columna
    por el texto de su encabezado, de modo que sigue funcionando si el sitio
    reordena columnas. Si el sitio cambia mucho su HTML, revisa esta función.
    """
    import requests
    from bs4 import BeautifulSoup

    proyectos: list[dict] = []
    for pagina in range(1, SEIA_MAX_PAGINAS + 1):
        params = {
            "tipoPresentacion": "AMBOS",
            "Pengan": "",
            "principal": "1",
            "estadoProyecto": "",
            "orderby": "5",   # ordenar por fecha
            "orderbyc": "DESC",
            "pagina": str(pagina),
        }
        if SEIA_SECTOR_ID:
            params["sector"] = str(SEIA_SECTOR_ID)
        try:
            r = requests.get(SEIA_URL, params=params, headers=HEADERS, timeout=45)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"[SEIA] Error consultando página {pagina}: {e}", file=sys.stderr)
            break

        soup = BeautifulSoup(r.text, "lxml")
        tabla = soup.find("table")
        if not tabla:
            print(f"[SEIA] No se encontró tabla en página {pagina}.", file=sys.stderr)
            break

        filas = tabla.find_all("tr")
        if len(filas) < 2:
            break

        # Mapear encabezados -> índice de columna.
        encabezados = [limpiar(th.get_text()).lower() for th in filas[0].find_all(["th", "td"])]

        def idx(*claves, default=None):
            for i, h in enumerate(encabezados):
                if any(c in h for c in claves):
                    return i
            return default

        i_nombre = idx("nombre", default=1)
        i_tipo = idx("tipo")
        i_region = idx("región", "region")
        i_tipologia = idx("tipología", "tipologia", "sector")
        i_titular = idx("titular", "razón", "razon", "empresa")
        i_inv = idx("inversión", "inversion", "mm")
        i_fecha = idx("fecha")
        i_estado = idx("estado")

        for fila in filas[1:]:
            celdas = fila.find_all("td")
            if len(celdas) < 3:
                continue

            def val(i):
                return limpiar(celdas[i].get_text()) if i is not None and i < len(celdas) else ""

            nombre = val(i_nombre)
            if not nombre:
                continue

            enlace = ""
            a = celdas[i_nombre].find("a") if i_nombre is not None and i_nombre < len(celdas) else None
            if a and a.get("href"):
                href = a["href"]
                enlace = href if href.startswith("http") else "https://seia.sea.gob.cl" + href

            registro = {
                "nombre": nombre,
                "tipo": val(i_tipo),            # DIA / EIA
                "region": val(i_region),
                "tipologia": val(i_tipologia),
                "titular": val(i_titular),
                "inversion_mmusd": val(i_inv),
                "fecha": val(i_fecha),
                "estado": val(i_estado),
                "enlace": enlace,
            }

            # Filtro de minería (por tipología/nombre) salvo que ya se filtre por sector.
            texto_check = " ".join([nombre, registro["tipologia"], registro["titular"]])
            if SEIA_SECTOR_ID or es_mineria(texto_check):
                proyectos.append(registro)

        time.sleep(1)  # cortesía con el servidor

    print(f"[SEIA] {len(proyectos)} proyectos mineros recolectados.", file=sys.stderr)
    return proyectos


# --------------------------------------------------------------------------
# Fuente 2: Google News RSS
# --------------------------------------------------------------------------

def fetch_news() -> list[dict]:
    import feedparser

    vistos = set()
    noticias: list[dict] = []
    for q in NEWS_QUERIES:
        url = (
            "https://news.google.com/rss/search"
            f"?q={requests_quote(q)}&hl=es-419&gl=CL&ceid=CL:es-419"
        )
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            print(f"[News] Error en consulta '{q}': {e}", file=sys.stderr)
            continue

        for entry in feed.entries:
            titulo = limpiar(getattr(entry, "title", ""))
            enlace = getattr(entry, "link", "")
            if not titulo or enlace in vistos:
                continue
            if not es_mineria(titulo):
                continue
            vistos.add(enlace)

            # Google News pone la fuente al final del título: "Titular - Fuente"
            fuente = ""
            if hasattr(entry, "source") and getattr(entry.source, "title", ""):
                fuente = entry.source.title
            elif " - " in titulo:
                fuente = titulo.rsplit(" - ", 1)[-1]

            noticias.append({
                "titulo": titulo,
                "enlace": enlace,
                "fuente": fuente,
                "fecha": getattr(entry, "published", ""),
            })

    print(f"[News] {len(noticias)} noticias recolectadas.", file=sys.stderr)
    return noticias


def requests_quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s)


# --------------------------------------------------------------------------
# Fuente 3: Oportunidades para Recursos y Reservas (Claude API + web_search)
# --------------------------------------------------------------------------

def fetch_oportunidades_rr() -> list[dict]:
    """Investiga oportunidades comerciales para el área de R&R vía Claude API
    (web_search + salida estructurada). Nunca es fatal: si falla, se registra el
    motivo en stderr y se devuelve una lista vacía, para que SEIA y prensa (que
    son gratis) nunca dependan de esta parte de pago.

    Configurado para minimizar costo: modelo claude-sonnet-5 (no opus), effort
    "low", y máximo 4 búsquedas web por corrida. Ver README para cómo ajustar
    esto si la calidad de las oportunidades detectadas no convence.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[Oportunidades R&R] ANTHROPIC_API_KEY no está definida; se omite "
              "esta sección.", file=sys.stderr)
        return []

    import anthropic
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": OPORTUNIDADES_PROMPT}]
    response = None
    try:
        for _ in range(4):  # 1 intento + hasta 3 reintentos por pause_turn
            response = client.messages.create(
                model="claude-sonnet-5",
                max_tokens=8000,
                messages=messages,
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}],
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": OPORTUNIDADES_SCHEMA},
                },
            )
            if response.stop_reason == "pause_turn":
                messages = [messages[0], {"role": "assistant", "content": response.content}]
                continue
            break

        if response is None or response.stop_reason == "pause_turn":
            print("[Oportunidades R&R] Investigación no terminó tras varios "
                  "pause_turn; se omite esta corrida.", file=sys.stderr)
            return []
        if response.stop_reason == "refusal":
            print("[Oportunidades R&R] La API rechazó la solicitud.", file=sys.stderr)
            return []

        texto = next(b.text for b in response.content if b.type == "text")
        oportunidades = json.loads(texto).get("oportunidades", [])
        print(f"[Oportunidades R&R] {len(oportunidades)} oportunidades recolectadas.",
              file=sys.stderr)
        return oportunidades
    except Exception as e:  # noqa: BLE001
        print(f"[Oportunidades R&R] Error consultando la API de Claude: {e}", file=sys.stderr)
        return []


# --------------------------------------------------------------------------
# Datos de muestra (para probar sin red)
# --------------------------------------------------------------------------

def sample_data() -> dict:
    return {
        "proyectos": [
            {"nombre": "Ampliación Planta Concentradora Los Bronces", "tipo": "EIA",
             "region": "Metropolitana", "tipologia": "i.1 Minería",
             "titular": "Anglo American Sur S.A.", "inversion_mmusd": "3.100",
             "fecha": "2026-08-28", "estado": "En Calificación",
             "enlace": "https://seia.sea.gob.cl/"},
            {"nombre": "Proyecto Litio Salar de Maricunga", "tipo": "EIA",
             "region": "Atacama", "tipologia": "i.1 Minería",
             "titular": "Minera Salar Blanco SpA", "inversion_mmusd": "1.850",
             "fecha": "2026-08-26", "estado": "En Calificación",
             "enlace": "https://seia.sea.gob.cl/"},
            {"nombre": "Continuidad Operacional Mina Sur", "tipo": "DIA",
             "region": "Antofagasta", "tipologia": "i.1 Minería",
             "titular": "Codelco División Chuquicamata", "inversion_mmusd": "420",
             "fecha": "2026-08-25", "estado": "Aprobado",
             "enlace": "https://seia.sea.gob.cl/"},
            {"nombre": "Depósito de Relaves Filtrados El Tránsito", "tipo": "DIA",
             "region": "Coquimbo", "tipologia": "i.1 Minería",
             "titular": "Compañía Minera del Pacífico", "inversion_mmusd": "95",
             "fecha": "2026-08-22", "estado": "Rechazado",
             "enlace": "https://seia.sea.gob.cl/"},
        ],
        "noticias": [
            {"titulo": "Codelco acelera plan de inversiones en cobre para 2027",
             "enlace": "https://example.com/1", "fuente": "Diario Financiero",
             "fecha": "Mon, 01 Sep 2026 09:00:00 GMT"},
            {"titulo": "Nuevo proyecto de litio en Atacama ingresa al SEIA",
             "enlace": "https://example.com/2", "fuente": "Minería Chilena",
             "fecha": "Sun, 31 Aug 2026 18:30:00 GMT"},
            {"titulo": "Comunidades de Coquimbo objetan proyecto minero por uso de agua",
             "enlace": "https://example.com/3", "fuente": "BioBioChile",
             "fecha": "Sat, 30 Aug 2026 12:15:00 GMT"},
        ],
        "oportunidades": [
            {"proyecto": "Prospecto Cerro Alto", "empresa": "Explorer Andina SpA",
             "region": "Atacama", "linea_servicio": "Exploración y permisos (proyecto nuevo)",
             "relevancia": "Anunció 40 sondajes de confirmación; probable primera "
                            "estimación de recursos bajo JORC en el próximo trimestre.",
             "fuente_url": "https://example.com/cerro-alto", "fecha": "2026-08-27"},
            {"proyecto": "Distrito Puna Norte", "empresa": "Northern Junior Mining (TSX-V)",
             "region": "Antofagasta", "linea_servicio": "Auditoría / debida diligencia de recursos",
             "relevancia": "Levantó financiamiento y cambió de operador local; procesos "
                            "de este tipo suelen requerir auditoría independiente del "
                            "modelo de recursos.",
             "fuente_url": "https://example.com/puna-norte", "fecha": "2026-08-24"},
        ],
    }


# --------------------------------------------------------------------------
# Orquestación
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true",
                        help="Genera datos de muestra sin acceder a la red.")
    args = parser.parse_args()

    ahora = datetime.now(timezone.utc)

    if args.sample:
        datos = sample_data()
    else:
        datos = {
            "proyectos": fetch_seia(),
            "noticias": fetch_news(),
            "oportunidades": fetch_oportunidades_rr(),
        }

    corrida = {
        "generado_utc": ahora.isoformat(),
        "generado_legible": ahora.strftime("%Y-%m-%d %H:%M UTC"),
        "resumen": {
            "n_proyectos": len(datos["proyectos"]),
            "n_noticias": len(datos["noticias"]),
            "n_oportunidades": len(datos["oportunidades"]),
        },
        "proyectos": datos["proyectos"],
        "noticias": datos["noticias"],
        "oportunidades": datos["oportunidades"],
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # latest.json (lo que lee el dashboard)
    (DATA_DIR / "latest.json").write_text(
        json.dumps(corrida, ensure_ascii=False, indent=2), encoding="utf-8")

    # history.json (acumulado, para tendencias)
    hist_path = DATA_DIR / "history.json"
    historial = []
    if hist_path.exists():
        try:
            historial = json.loads(hist_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            historial = []
    historial.append({
        "fecha": ahora.strftime("%Y-%m-%d"),
        "n_proyectos": corrida["resumen"]["n_proyectos"],
        "n_noticias": corrida["resumen"]["n_noticias"],
        "n_oportunidades": corrida["resumen"]["n_oportunidades"],
    })
    hist_path.write_text(json.dumps(historial, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    print(f"OK: {corrida['resumen']['n_proyectos']} proyectos, "
          f"{corrida['resumen']['n_noticias']} noticias, "
          f"{corrida['resumen']['n_oportunidades']} oportunidades -> {DATA_DIR}")


if __name__ == "__main__":
    main()
