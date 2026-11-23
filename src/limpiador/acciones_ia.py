"""Motor de las acciones IA: `resumir-texto` y `clasificar-ficheros`.

Diseño (mantiene la separación lógica / interfaz):

- Este módulo NO importa Typer ni Rich: las acciones devuelven
  `(bitacora, exit_code, ruta_log)` para que la CLI solo decore. Por eso se
  testa sin CLI y sin red.
- Usa el centro vía `limpiador.ia.CentroIA` (httpx 0.28; la auditoría
  `proxies`→`proxy`/`mounts` está documentada allí y en el ADR-0002). Si no
  hay key o falla la conexión, la acción NO peta: degrada a heurística local y
  devuelve `EXIT_OFFLINE` (4).
- Todo texto que sale a consola o log pasa por `redact`, incluida la clave que
  un error de httpx pudiera arrastrar. Las rutas se redactan solo en el log.

Heurística local (modo offline, determinista):
- `resumir-texto`: primeras N frases + nota de longitud.
- `clasificar-ficheros`: por palabras clave del contenido y, si nada casa, por
  extensión; si nada, `sin-clasificar`.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from limpiador.acciones import Operacion
from limpiador.errores import EXIT_OFFLINE, EXIT_OK
from limpiador.ia import CentroIA, SinRedError
from limpiador.secretos import redact

if TYPE_CHECKING:  # solo tipos: evita el ciclo acciones <-> acciones_ia
    from limpiador.config import Accion

# Subcarpetas/archivos de salida (relativos y seguros, dentro de la carpeta).
DIR_RESUMENES: Final[str] = "resumenes"
ARCHIVO_LOG: Final[str] = "log_ia.md"

# Nº máximo de frases de la heurística de resumen offline.
FRASES_RESUMEN: Final[int] = 3

# Etiquetas (subcarpetas) de la clasificación. Rutas relativas seguras fijas.
ETIQUETAS_CLASIFICAR: Final[tuple[str, ...]] = (
    "codigo",
    "datos",
    "apuntes",
    "informes",
    "sin-clasificar",
)

# Palabras clave por etiqueta para la heurística offline (orden = prioridad).
_CLAVES_POR_ETIQUETA: Final[dict[str, tuple[str, ...]]] = {
    "codigo": ("def ", "class ", "import ", "función", "funcion", "return",
               "console.", "public ", "private ", "#include", "<html", "print("),
    "datos": ("timestamp", "usuario", "fecha", "hora", "valor", "registro",
              "email", "id,", ",", ";"),
    "informes": ("informe", "conclusión", "conclusion", "objetivo", "resultado",
                 "introducción", "introduccion", "memoria"),
    "apuntes": ("tema", "apuntes", "examen", "resumen", "capítulo", "capitulo",
                "lección", "leccion", "concepto", "define"),
}
_EXTENSIONES_ETIQUETA: Final[dict[str, tuple[str, ...]]] = {
    "codigo": (".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".html", ".css"),
    "datos": (".csv", ".tsv", ".json", ".jsonl", ".xml", ".yml", ".yaml"),
    "informes": (".pdf", ".docx", ".odt"),
    "apuntes": (".md", ".txt", ".rst", ".org"),
}

_SPLIT_FRASES: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")


class IAError(Exception):
    """Error de una acción IA que sí debe abortar (modo estricto o fallo disco)."""


class IAccion(Protocol):
    """Vista mínima de `config.Accion` que necesitan las acciones IA.

    Atributos `@property` (solo lectura): `config.Accion` es un modelo pydantic
    `frozen`, y un protocolo con variables mutables no lo aceptaría.
    """

    @property
    def operacion(self) -> str: ...

    @property
    def patrones(self) -> tuple[str, ...]: ...

    @property
    def modelo(self) -> str | None: ...

    @property
    def prompt(self) -> str | None: ...

    @property
    def modo_offline(self) -> str | None: ...


# --------------------------------------------------------------------------- #
# Planificación (para --simular): no llama al centro ni escribe.
# --------------------------------------------------------------------------- #
def planificar_ia(
    accion: Accion, raiz: Path, objetivos: list[Path]
) -> list[Operacion]:
    """Plan de una acción IA sobre `objetivos`, sin escribir ni llamar a la IA."""
    plan: list[Operacion] = []
    for origen in objetivos:
        if accion.operacion == "resumir-texto":
            destino = f"{DIR_RESUMENES}/resumen-{origen.stem}.md"
        else:
            destino = f"{DIR_RESUMENES}/... (por contenido)"
        plan.append(Operacion(accion.operacion, origen, destino))
    return plan


# --------------------------------------------------------------------------- #
# Lectura y heurísticas (sin red).
# --------------------------------------------------------------------------- #
def leer_texto(fichero: Path) -> str:
    """Lee un fichero de texto tolerante; ilegible -> texto vacío."""
    try:
        return fichero.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _frases(texto: str) -> list[str]:
    limpio = re.sub(r"\s+", " ", texto).strip()
    if not limpio:
        return []
    return [f.strip() for f in _SPLIT_FRASES.split(limpio) if f.strip()]


def resumen_heuristico(texto: str) -> str:
    """Resumen offline determinista: primeras N frases + nota de longitud."""
    frases = _frases(texto)
    palabras = len(re.findall(r"\w+", texto))
    lineas = texto.count("\n") + (1 if texto else 0)
    cabecera = " ".join(frases[:FRASES_RESUMEN]) if frases else "(sin texto reconocible)"
    return (
        f"Resumen (heurística local, sin IA):\n\n{cabecera}\n\n"
        f"— {len(frases)} frase(s), {palabras} palabra(s), {lineas} línea(s) de origen."
    )


def _etiqueta_por_contenido(nombre: str, texto: str) -> str:
    muestra = texto.lower()[:4000]
    mejor, mejor_puntuacion = "", 0
    for etiqueta, claves in _CLAVES_POR_ETIQUETA.items():
        puntuacion = sum(1 for c in claves if c.lower() in muestra)
        if puntuacion > mejor_puntuacion:
            mejor, mejor_puntuacion = etiqueta, puntuacion
    if mejor and mejor_puntuacion >= 2:
        return mejor
    sufijo = Path(nombre).suffix.lower()
    for etiqueta, extensiones in _EXTENSIONES_ETIQUETA.items():
        if sufijo in extensiones:
            return etiqueta
    return "sin-clasificar"


def clasificar_heuristica(nombre: str, texto: str) -> str:
    """Subcarpeta heurística para un fichero (siempre una etiqueta válida)."""
    etiqueta = _etiqueta_por_contenido(nombre, texto)
    return etiqueta if etiqueta in ETIQUETAS_CLASIFICAR else "sin-clasificar"


# --------------------------------------------------------------------------- #
# Prompts hacia el centro.
# --------------------------------------------------------------------------- #
def _prompt_resumir(texto: str, accion: IAccion) -> str:
    base = accion.prompt or (
        "Resume el siguiente texto en un párrafo breve, en español, respetando "
        "las ideas clave. Termina indicando cuántas palabras tenía el original."
    )
    return f"{base}\n\n--- TEXTO ---\n{texto[:8000]}"


def _prompt_clasificar(nombre: str, texto: str, accion: IAccion) -> str:
    base = accion.prompt or (
        "Clasifica el siguiente fichero en UNA categoría, respondiendo SOLO el "
        f"nombre de la categoría entre: {', '.join(ETIQUETAS_CLASIFICAR)}."
    )
    return f"{base}\n\nFichero: {nombre}\n--- CONTENIDO ---\n{texto[:4000]}"


def _etiqueta_desde_respuesta(respuesta: str) -> str:
    bajo = respuesta.strip().lower()
    for etiqueta in ETIQUETAS_CLASIFICAR:
        if etiqueta in bajo:
            return etiqueta
    # Sin etiqueta literal: se reduce a una etiqueta válida por token con
    # acentos/tildes quitados ("Código." -> "codigo"). Nunca se devuelve
    # texto crudo: evitaría carpetas basura sacadas de la prosa del modelo.
    sin_accents = unicodedata.normalize("NFKD", bajo).encode("ascii", "ignore").decode()
    tokens: list[str] = re.findall(r"[a-z][a-z-]*", sin_accents)
    for token in tokens:
        if token in ETIQUETAS_CLASIFICAR:
            return token
    return "sin-clasificar"


# --------------------------------------------------------------------------- #
# Ejecución (llama al centro o degrada).
# --------------------------------------------------------------------------- #
def _intentar(
    llamada: object,
    *,
    estricto: bool,
) -> tuple[str, bool, str]:
    """Llama al centro. Si falla: offline+motivo, o `IAError` si `estricto`.

    Devuelve (contenido, offline, motivo_ya_reductado). Nunca propaga un error
    con la clave en claro: el motivo pasa por `redact`.
    """
    try:
        return str(llamada()), False, ""  # type: ignore[operator]
    except SinRedError as exc:
        motivo = redact(str(exc))
        if estricto:
            raise IAError(motivo) from exc
        return "", True, motivo


def ejecutar_resumir(
    accion: IAccion,
    raiz: Path,
    objetivos: list[Path],
    centro: CentroIA | None = None,
) -> tuple[list[str], int, Path | None]:
    """Escribe un resumen por fichero. Offline -> heurística + exit 4."""
    centro = centro if centro is not None else CentroIA.desde_entorno()
    bitacora: list[str] = []
    linea_log: list[str] = []
    degradado = False
    destino_dir = raiz / DIR_RESUMENES
    for origen in objetivos:
        texto = leer_texto(origen)
        contenido, offline, motivo = _intentar(
            lambda t=texto: centro.completar(
                _prompt_resumir(t, accion), modelo=accion.modelo, max_tokens=512
            ).contenido,
            estricto=accion.modo_offline == "estricto",
        )
        if offline:
            degradado = True
            contenido = resumen_heuristico(texto)
            motivo = motivo or "sin conexión"
        destino = _ruta_libre(destino_dir / f"resumen-{origen.stem}.md")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(_cabecera_resumen(origen, contenido, offline), encoding="utf-8")
        bitacora.append(
            f"[modo offline] resumen de {origen.name} -> "
            + f"{destino.relative_to(raiz)}"
            if offline
            else f"resumen de {origen.name} -> {destino.relative_to(raiz)}"
        )
        linea_log.append(
            f"- {origen.name}: "
            + ("offline " + (motivo or "") if offline else "IA " + (accion.modelo or "centro"))
        )
    exit_code = EXIT_OFFLINE if degradado else EXIT_OK
    return bitacora, exit_code, _escribir_log(raiz, "resumir-texto", linea_log)


def ejecutar_clasificar(
    accion: IAccion,
    raiz: Path,
    objetivos: list[Path],
    centro: CentroIA | None = None,
) -> tuple[list[str], int, Path | None]:
    """Copia ficheros a subcarpetas por clase. Offline -> heurística + exit 4.

    No destructivo: el original se queda; solo se crean copias clasificadas.
    """
    centro = centro if centro is not None else CentroIA.desde_entorno()
    bitacora: list[str] = []
    linea_log: list[str] = []
    degradado = False
    for origen in objetivos:
        texto = leer_texto(origen)
        respuesta, offline, motivo = _intentar(
            lambda n=origen.name, t=texto: centro.completar(
                _prompt_clasificar(n, t, accion), modelo=accion.modelo, max_tokens=16
            ).contenido,
            estricto=accion.modo_offline == "estricto",
        )
        if offline:
            degradado = True
            etiqueta = clasificar_heuristica(origen.name, texto)
            motivo = motivo or "sin conexión"
        else:
            etiqueta = _etiqueta_desde_respuesta(respuesta)
        destino_dir = _ruta_dentro(raiz, etiqueta)
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = _ruta_libre(destino_dir / origen.name)
        _copiar(origen, destino)
        bitacora.append(
            f"[modo offline] clasificado {origen.name} -> {etiqueta}/{destino.name}"
            if offline
            else f"clasificado {origen.name} -> {etiqueta}/{destino.name}"
        )
        linea_log.append(
            f"- {origen.name}: {etiqueta} ("
            + ("offline " + (motivo or "") if offline else "IA " + (accion.modelo or "centro"))
            + ")"
        )
    exit_code = EXIT_OFFLINE if degradado else EXIT_OK
    return bitacora, exit_code, _escribir_log(raiz, "clasificar-ficheros", linea_log)


# --------------------------------------------------------------------------- #
# Utilidades de salida seguras.
# --------------------------------------------------------------------------- #
def _cabecera_resumen(origen: Path, contenido: str, offline: bool) -> str:
    fuente = "heurística local (modo offline)" if offline else "IA del centro"
    return f"<!-- resumen de {origen.name} vía {fuente} -->\n\n{contenido}\n"


def _ruta_dentro(raiz: Path, sub: str) -> Path:
    """`raiz/sub` garantizando contención dentro de `raiz`."""
    destino = (raiz / sub).resolve()
    try:
        destino.relative_to(raiz.resolve())
    except ValueError as exc:  # pragma: no cover - etiquetas fijas y seguras
        raise IAError(f"la carpeta '{sub}' quedaría fuera del destino") from exc
    return destino


def _ruta_libre(destino: Path) -> Path:
    if not destino.exists():
        return destino
    for i in range(1, 10_000):
        alternativo = destino.with_name(f"{destino.stem}-{i}{destino.suffix}")
        if not alternativo.exists():
            return alternativo
    raise IAError(f"demasiadas colisiones para '{destino.name}'")  # pragma: no cover


def _copiar(origen: Path, destino: Path) -> None:
    destino.write_bytes(origen.read_bytes())


def _escribir_log(raiz: Path, operacion: str, lineas: list[str]) -> Path:
    """Anexa una entrada al log de auditoría (todo el contenido, redactado)."""
    destino_dir = raiz / DIR_RESUMENES
    destino_dir.mkdir(parents=True, exist_ok=True)
    ruta = destino_dir / ARCHIVO_LOG
    cabecera = f"\n\n## {datetime.now().isoformat(timespec='seconds')} · {operacion}\n"
    cuerpo = cabecera + "\n".join(redact(linea) for linea in lineas) + "\n"
    with ruta.open("a", encoding="utf-8") as fichero:
        fichero.write(cuerpo)
    return ruta


# --------------------------------------------------------------------------- #
# Punto de entrada del motor IA (la CLI solo llama aquí; separación total).
# --------------------------------------------------------------------------- #
def planificar_ia_desde(
    accion: Accion, carpeta: Path
) -> tuple[list[Operacion], Path, list[Path], bool]:
    """`(plan, raiz_resuelta, objetivos, habia_objetivos)` para la CLI.

    Resuelve y valida la carpeta UNA vez y reutiliza el glob para el plan y
    para la ejecución posterior (`--si`), sin duplicar trabajo.
    """
    from limpiador.acciones import (  # lazy: ciclo acciones <-> acciones_ia
        comprobar_carpeta_resuelta,
        ficheros_que_coinciden,
        planificar_desde_objetivos,
    )

    _, raiz = comprobar_carpeta_resuelta(carpeta)
    objetivos = ficheros_que_coinciden(accion, raiz)
    plan = planificar_desde_objetivos(accion, raiz, objetivos)
    return plan, raiz, objetivos, bool(plan)


def ejecutar_ia(
    accion: Accion,
    raiz: Path,
    objetivos: list[Path],
    centro: CentroIA | None = None,
) -> tuple[list[str], int, Path | None]:
    """Despacha a la acción IA concreta. `(bitácora, exit_code, ruta_log)`.

    Exit codes: 0 con IA real, 4 completado en modo degradado (heurística),
    1 si el modo `estricto` se niega a degradar (`IAError`). La interfaz
    (Typer/Rich) no aparece aquí: esto es motor puro y se testa sin CLI.
    """
    try:
        if accion.operacion == "resumir-texto":
            return ejecutar_resumir(accion, raiz, objetivos, centro)
        if accion.operacion == "clasificar-ficheros":
            return ejecutar_clasificar(accion, raiz, objetivos, centro)
    except SinRedError as exc:  # pragma: no cover - `_intentar` ya lo traga
        raise IAError(redact(str(exc))) from exc
    raise IAError(f"operación IA desconocida: {accion.operacion}")
