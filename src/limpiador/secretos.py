"""Redacción de secretos y detección de patrones de API key.

Dos responsabilidades, un mismo módulo, para que la *definición* de «qué es un
secreto» esté en un único sitio:

1. `redact(texto)` — enmascara cualquier secreto ANTES de imprimirlo o
   escribirlo en un log. Si un mensaje de error de httpx (o cualquier otra
   cadena) contiene la API key del centro, un `Bearer ...` o un patrón
   `sk-...`, sale ya enmascarado. Así «sin filtrar la clave» = la clave nunca
   aparece en la salida ni en el historial de logs.

2. `PATRONES_API_KEY` — las mismas expresiones regulares sirven para el
   escáner del repositorio (`scripts/escaner_secretos.py` /
   `tests/test_secretos.py`): si un fichero versionado casa con cualquiera de
   ellas, CI bloquea el *merge*. Es la garantía mecánica de «ninguna clave en
   el historial».

No se guarda NINGÚN valor de clave en este módulo ni en el repositorio: solo
patrones. La clave real vive en `.env` (ignorado) o en el entorno.
"""

from __future__ import annotations

import re
from typing import Final

# Máscara fija: ni longitud ni prefijos reales del secreto.
MASCARA: Final[str] = "[REDACTADO]"

# --- Patrones de secreción -------------------------------------------------
# Ordenados: los de esquema (Bearer/Basic) y los de prefijo (`sk-...`, tokens
# de servicio). Cada patrón captura TODO el secreto para poder sustituirlo por
# `MASCARA` sin dejar restos.
_PATRON_BEARER: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(authorization\s*:\s*)?bearer\s+[a-z0-9._~+/=-]{6,}"
)
_PATRON_BASIC: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(authorization\s*:\s*)?basic\s+[a-z0-9+/=._~-]{6,}"
)
# Claves con prefijo tipo OpenAI / servicios del centro: sk-, pk-, key-,
# apikey-, token-, secret-... (guión o bajo, al menos 8 caracteres).
_PATRON_PREFIJO: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:sk|pk|api[_-]?key|apikey|token|secret|access[_-]?token|ghp|gho|ghs|github_pat)"
    r"[_-][a-z0-9_\-]{6,}"
)
# Encadenado tras `Bearer ` ya lo cubre _PATRON_BEARER; además cazamos la forma
# `clave=sk-...` o `"api_key": "..."` explícita.
_PATRON_ASIGNACION: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|secret[_-]?key|"
    r"secret|password|passwd|pwd)\b[\"']?\s*[:=]\s*"
    r"(?:\"[^\"]{6,}\"|'[^']{6,}'|[^\s,;\"']{6,})"
)

# Lista de patrones usados por `redact`.
_PATRONES_REDACT: Final[tuple[re.Pattern[str], ...]] = (
    _PATRON_BEARER,
    _PATRON_BASIC,
    _PATRON_PREFIJO,
    _PATRON_ASIGNACION,
)

# Patrones usados por el ESCÁNER del repositorio. Se mantiene separada para
# poder afinar umbrales sin afectar a `redact`.
_PATRON_ESCANER_KEY: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bsk-[a-z0-9_\-]{8,}\b"
)
_PATRON_ESCANER_BEARER: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}"
)
_PATRON_ESCANER_OPENAI: Final[re.Pattern[str]] = re.compile(
    r"\bsk-[A-Za-z0-9_\-]{20,}\b"
)
_PATRON_ESCANER_ASIGNACION: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|secret[_-]?key)\b[\"']?\s*[:=]\s*"
    r"[\"'][^\"'\n]{8,}[\"']"
)

# Patrones de FALSO POSITIVO que el escáner tolera (docs, tests y el propio
# código de este módulo hablan DE claves sin contener ninguna). Un literal
# marcado con `# scannner: ejemplo` es, por definición, un ejemplo falso: el
# detector lo ignora. El marcador usa `nn` para NO autodetectarse.
_PERMITIDO_ESCANER: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\[redactad", re.IGNORECASE),
    re.compile(r"\bREDACTAD\w*\b"),
    re.compile(r"\bsk-\[?[Xx*]{2,}"),
    re.compile(r"ejemplo|sample|placeholder|exemplo|tu-?\s?api|my-?api", re.IGNORECASE),
    re.compile(r"#\s*scan{2}er:\s*ejemplo"),
)

# Patrones con los que el escáner escanea todo el repo (selección dura, para el
# job de CI): si una línea casa con UNO de estos y NO con ninguno de
# `_PERMITIDO_ESCANER`, se considera fuga.
PATRONES_API_KEY: Final[tuple[re.Pattern[str], ...]] = (
    _PATRON_ESCANER_KEY,
    _PATRON_ESCANER_BEARER,
    _PATRON_ESCANER_OPENAI,
    _PATRON_ESCANER_ASIGNACION,
)


def redact(texto: str, *, secretos: tuple[str, ...] = ()) -> str:
    """Devuelve `texto` con toda la clave/patrón de secreto enmascarado.

    Se aplica SIEMPRE antes de imprimir o loguear cualquier cadena que pueda
    llevar un secreto (mensajes de error de httpx, volcados de configuración,
    trazas). Si `secretos` trae claves concretas conocidas (p. ej. la del
    entorno), se sustituyen literalmente además de por patrón, por si la key
    no tuviera un prefijo reconocible.

    Es idempotente: redactar dos veces el mismo texto no cambia el resultado.
    """
    if not texto:
        return texto
    resultado = texto
    # 1) Sustitución literal de secretos conocidos (exacta, insensible a forma).
    for secreto in secretos:
        if secreto and secreto in resultado:
            resultado = resultado.replace(secreto, MASCARA)
    # 2) Sustitución por patrón (Bearer/Basic, sk-..., asignaciones).
    for patron in _PATRONES_REDACT:
        resultado = patron.sub(MASCARA, resultado)
    return resultado


def contiene_secreto(linea: str) -> bool:
    """True si `linea` contiene un patrón de API key que no sea un ejemplo."""
    if not any(p.search(linea) for p in PATRONES_API_KEY):
        return False
    return not any(p.search(linea) for p in _PERMITIDO_ESCANER)
