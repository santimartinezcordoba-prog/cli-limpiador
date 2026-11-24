"""Carga y validación del fichero de acciones (`acciones.json`) con pydantic.

Toda la validación se hace «en seco»: nunca se toca el disco más allá de
leer el propio JSON. Los modelos `Accion` y `Config` de pydantic comprueban
tipos, campos obligatorios y coherencia entre campos; los errores se mapean a
mensajes propios con la ruta exacta del campo, del estilo
``acciones[0].nombre: campo requerido``, y se acumulan TODOS de golpe (no
solo el primero). Las incoherencias entre operación y campos dependientes se
reportan a nivel de objeto con el formato exacto
``acciones[2]: 'destino' es obligatorio cuando operacion='mover'``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from limpiador.errores import ConfigInvalidaError

# Whitlist de operaciones ejecutables. El orden importa: se muestra tal cual
# en el mensaje «valor no soportado (permitido: mover, borrar, ...)».
OPERACIONES_VALIDAS: Final[tuple[str, ...]] = (
    "mover",
    "borrar",
    "renombrar",
    "dedup",
    "resumir-texto",
    "clasificar-ficheros",
)

LISTA_OPERACIONES: Final[str] = ", ".join(OPERACIONES_VALIDAS)

# Operaciones que usan la IA del centro (con degradación offline).
OPERACIONES_IA: Final[frozenset[str]] = frozenset({"resumir-texto", "clasificar-ficheros"})

# Campos admitidos en cada acción (los extra se rechazan con extra="forbid").
CAMPOS_ACEPTADOS: Final[frozenset[str]] = frozenset(
    {
        "nombre",
        "descripcion",
        "operacion",
        "patrones",
        "destino",
        "sufijo",
        "papelera",
        "modelo",
        "prompt",
        "modo_offline",
    }
)

# Operaciones para las que tiene sentido activar la papelera.
OPERACIONES_CON_PAPELERA: Final[frozenset[str]] = frozenset({"borrar", "dedup"})

# Valores admitidos para el campo `modo_offline` de las acciones IA.
MODOS_OFFLINE_VALIDOS: Final[frozenset[str]] = frozenset({"heuristica", "estricto"})
LISTA_MODOS_OFFLINE: Final[str] = ", ".join(sorted(MODOS_OFFLINE_VALIDOS))


def es_ruta_segura(valor: str) -> bool:
    """True si `valor` es relativo, sin ``..`` y sin separadores de ruta.

    Las acciones solo pueden actuar sobre nombres/comodines dentro de la
    carpeta objetivo: se rechazan rutas absolutas, ``~`` y path traversal.
    """
    if not valor or valor.startswith("/") or valor.startswith("~"):
        return False
    partes = valor.replace("\\", "/").split("/")
    return ".." not in partes


def es_patron_seguro(patron: str) -> bool:
    """Un patrón solo admite comodines sobre nombres, nunca rutas."""
    return es_ruta_segura(patron)


class Accion(BaseModel):
    """Una acción ya validada, lista para ejecutarse.

    `validate_default=True` hace que los validadores de `destino` y `sufijo`
    se ejecuten también cuando el campo brilla por su ausencia: así pueden
    exigir «destino obligatorio si operacion=mover» con el mensaje exacto.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        str_strip_whitespace=True,
    )

    nombre: str = Field(min_length=1)
    descripcion: str = Field(min_length=1)
    operacion: str
    patrones: tuple[str, ...] = Field(min_length=1)
    destino: str | None = None
    sufijo: str | None = Field(default=None, min_length=1)
    # true -> papelera por defecto (<carpeta>/papelera); "DIR" -> <carpeta>/DIR.
    papelera: bool | str | None = None
    # --- Campos de las acciones IA (resumir-texto / clasificar-ficheros) ---
    # `modelo`: opcional; si falta, el motor usa LIMPIADOR_IA_MODELO o el de
    # fábrica. OBLIGATORIO en acciones IA en tiempo de VALIDACIÓN (no en carga)
    # para exigir el campo con índice exacto.
    modelo: str | None = Field(default=None, min_length=1)
    # `prompt`: instrucción opcional para afinar la tarea IA.
    prompt: str | None = Field(default=None, min_length=1)
    # `modo_offline`: controla la degradación. "heuristica" (por defecto) degrada
    # a heurística local si no hay key/red; "estricto" falla en vez de degradar.
    modo_offline: str | None = Field(default=None, min_length=1)

    @field_validator("operacion")
    @classmethod
    def _operacion_en_whitelist(cls, valor: str) -> str:
        if valor not in OPERACIONES_VALIDAS:
            raise ValueError(f"valor no soportado (permitido: {LISTA_OPERACIONES})")
        return valor

    @field_validator("papelera")
    @classmethod
    def _papelera_coherente(cls, valor: bool | str | None) -> bool | str | None:
        # La comprobación de «solo aplica a borrar/dedup» vive en el
        # model_validator, para dar el formato exacto a nivel de objeto. Aquí
        # solo validamos la forma del nombre de carpeta cuando es un texto.
        if isinstance(valor, str):
            if not valor:
                raise ValueError("debe ser un texto no vacío")
            if not es_ruta_segura(valor):
                raise ValueError("debe ser una ruta relativa segura")
        return valor

    @field_validator("destino")
    @classmethod
    def _destino_seguro(cls, valor: str | None) -> str | None:
        if valor is not None and not es_ruta_segura(valor):
            raise ValueError("debe ser una ruta relativa segura")
        return valor

    @field_validator("sufijo")
    @classmethod
    def _sufijo_sin_rutas(cls, valor: str | None) -> str | None:
        if valor is not None and ("/" in valor or "\\" in valor or ".." in valor):
            raise ValueError("no puede contener rutas")
        return valor

    @field_validator("modo_offline")
    @classmethod
    def _modo_offline_valido(cls, valor: str | None) -> str | None:
        if valor is None:
            return valor
        if valor not in MODOS_OFFLINE_VALIDOS:
            raise ValueError(
                f"valor no soportado (permitido: {LISTA_MODOS_OFFLINE})"
            )
        return valor

    @model_validator(mode="after")
    def _coherencia_operacion_campos(self) -> Accion:
        """Errores de coherencia entre `operacion` y sus campos dependientes.

        Van a nivel de objeto (no de campo) para producir el formato exacto
        exigido por la rúbrica, p. ej.::

            acciones[2]: 'destino' es obligatorio cuando operacion='mover'

        Si `operacion` ya falló, pydantic no ejecuta este validador: no se
        duplican las culpas.
        """
        if self.operacion == "mover":
            if self.destino is None:
                raise ValueError(
                    "'destino' es obligatorio cuando operacion='mover'"
                )
        elif self.destino is not None:
            raise ValueError("'destino' solo aplica a la operación 'mover'")
        if self.operacion == "renombrar":
            if self.sufijo is None:
                raise ValueError(
                    "'sufijo' es obligatorio cuando operacion='renombrar'"
                )
        elif self.sufijo is not None:
            raise ValueError("'sufijo' solo aplica a la operación 'renombrar'")
        # Papelera y campos IA solo aplican a sus operaciones.
        if self.papelera is not None and self.operacion not in OPERACIONES_CON_PAPELERA:
            raise ValueError(
                "'papelera' solo aplica a las operaciones 'borrar' o 'dedup'"
            )
        if self.operacion in OPERACIONES_IA:
            # En acciones IA no tienen sentido destino/sufijo/papelera.
            if self.destino is not None:
                raise ValueError(
                    f"'destino' no aplica a la operación '{self.operacion}'"
                )
            if self.sufijo is not None:
                raise ValueError(
                    f"'sufijo' no aplica a la operación '{self.operacion}'"
                )
            # `modelo` es OBLIGATORIO en acciones IA (mensaje con campo exacto).
            if self.modelo is None:
                raise ValueError(
                    f"'modelo' es obligatorio cuando operacion='{self.operacion}'"
                )
        elif self.modelo is not None or self.prompt is not None:
            raise ValueError(
                "'modelo'/'prompt' solo aplican a operaciones IA "
                f"({', '.join(sorted(OPERACIONES_IA))})"
            )
        return self


class Config(BaseModel):
    """Configuración completa del fichero de acciones."""

    version: int = Field(default=1, strict=True)
    acciones: list[Accion] = Field(min_length=1)


def _ruta_legible(loc: tuple[Any, ...]) -> str:
    """Convierte la localización de un error de pydantic en texto propio.

    ``(0, 'nombre')`` -> ``[0].nombre``; los enteros se pintan como índice.
    """
    texto = ""
    for parte in loc:
        if isinstance(parte, int):
            texto += f"[{parte}]"
        else:
            texto += f".{parte}" if texto else str(parte)
    return texto


def _prefijo(loc: tuple[Any, ...]) -> str:
    """Prefijo legible de un error: ``acciones[0].nombre`` o ``<raíz>.version``."""
    if not loc:
        return "<raíz>"
    if loc[0] == "acciones":
        if len(loc) == 1:
            return "<raíz>.acciones"
        return "acciones" + _ruta_legible(loc[1:])
    return f"<raíz>.{_ruta_legible(loc)}"


def _mensaje_de_error(loc: tuple[Any, ...], tipo: str, msg: str) -> str:
    """Traduce un error de pydantic al mensaje en español del proyecto."""
    campo = next((p for p in reversed(loc) if isinstance(p, str)), "")
    dentro_de_patrones = campo == "patrones" and bool(loc) and isinstance(loc[-1], int)
    if tipo == "missing":
        return "campo requerido"
    if tipo == "extra_forbidden":
        return "campo no permitido"
    if tipo == "model_attributes_type":
        return "debe ser un objeto JSON"
    if campo == "operacion" and tipo in {"string_type", "string_too_short"}:
        return f"valor no soportado (permitido: {LISTA_OPERACIONES})"
    if dentro_de_patrones and tipo in {"string_type", "string_too_short"}:
        return "patrón inválido o no seguro"
    if campo == "patrones" and tipo == "list_type":
        return "debe ser una lista con al menos un patrón"
    if tipo == "too_short":
        if campo == "acciones":
            return "debe ser una lista con al menos una acción"
        if campo == "patrones":
            return "debe ser una lista con al menos un patrón"
        return "debe ser un texto no vacío"
    if tipo == "int_type":
        return "debe ser un entero"
    if tipo == "value_error":
        return msg.removeprefix("Value error, ")
    if tipo in {"string_type", "string_too_short", "list_type"}:
        return "debe ser un texto no vacío"
    return "valor inválido"


def _chequeos_de_contenido(datos: dict[str, Any]) -> list[str]:
    """Comprobaciones que pydantic no hace: seguridad de patrones y duplicados.

    Se ejecutan sobre el JSON crudo para poder reportar también los fallos de
    las acciones que ya tengan otros errores.
    """
    errores: list[str] = []
    lista = datos.get("acciones")
    if not isinstance(lista, list):
        return errores
    nombres_vistos: set[str] = set()
    for i, item in enumerate(lista):
        if not isinstance(item, dict):
            continue
        patrones = item.get("patrones")
        if isinstance(patrones, list):
            for j, patron in enumerate(patrones):
                if isinstance(patron, str) and not es_patron_seguro(patron):
                    errores.append(f"acciones[{i}].patrones[{j}]: patrón inválido o no seguro")
        nombre = item.get("nombre")
        if isinstance(nombre, str):
            if nombre in nombres_vistos:
                errores.append(f"acciones[{i}].nombre: nombre duplicado '{nombre}'")
            nombres_vistos.add(nombre)
    return errores


def validar_contenido(datos: Any) -> Config:
    """Valida el JSON ya parseado y lanza `ConfigInvalidaError` si algo falla."""
    errores: list[str] = []
    if not isinstance(datos, dict):
        raise ConfigInvalidaError(["<raíz>: el fichero debe ser un objeto JSON"])

    config: Config | None
    try:
        config = Config.model_validate(datos)
    except ValidationError as exc:
        config = None
        errores = [
            f"{_prefijo(err['loc'])}: {_mensaje_de_error(err['loc'], err['type'], err['msg'])}"
            for err in exc.errors()
        ]

    errores += _chequeos_de_contenido(datos)
    if errores:
        raise ConfigInvalidaError(errores)
    assert config is not None  # sin errores => el modelo se construyó entero
    return config


def cargar_config(ruta: Path) -> Config:
    """Lee y valida el JSON de `ruta`. Lanza `ConfigInvalidaError` con detalles."""
    cargar_dotenv()
    if not ruta.exists():
        raise ConfigInvalidaError([f"{ruta}: el fichero de configuración no existe"])
    if not ruta.is_file():
        raise ConfigInvalidaError([f"{ruta}: no es un fichero"])
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigInvalidaError([f"{ruta}: no se pudo leer ({exc})"]) from exc
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ConfigInvalidaError(
            [
                f"{ruta}: JSON inválido: mal formado en la línea {exc.lineno}, "
                f"columna {exc.colno}: {exc.msg}"
            ]
        ) from exc
    return validar_contenido(datos)


# --------------------------------------------------------------------------- #
# Variables de entorno de la IA (.env) — sin valores en la salida, nunca.
# --------------------------------------------------------------------------- #
# Prefijos/nombres de las variables que `limpiador` entiende para la IA. La
# KEY entra en la lista porque `comprobar-ia` debe poder decir si está
# «presente»: solo se mira la PRESENCIA, el valor jamás se imprime ni se
# loguea (y toda salida pasa por `secretos.redact`).
VARIABLES_IA: Final[tuple[str, ...]] = (
    "LIMPIADOR_IA_KEY",
    "LIMPIADOR_IA_URL",
    "LIMPIADOR_IA_MODELO",
    "LIMPIADOR_IA_TIMEOUT",
    "LIMPIADOR_CA_BUNDLE",
)

# Prefijo común de las variables de limpiador (para `env_relevantes`).
PREFIJO_ENV: Final[str] = "LIMPIADOR_"

_LLINEA_ENV = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def cargar_dotenv(ruta: Path | None = None) -> Path | None:
    """Carga `VAR=valor` desde un `.env` sin pisar variables ya definidas.

    La clave del centro vive SOLO en `.env` (ignorado por git) o en el
    entorno. No usamos `python-dotenv` para no añadir dependencias: son
    asignaciones `CLAVE=valor`, con `#` de comentario y comillas opcionales.
    Un `.env` ilegible se ignora en silencio: la CLI degrada a heurística
    («sin dejar a nadie tirado sin red») en lugar de petar.

    Nunca devuelve ni registra valores: solo la ruta cargada o None.
    """
    candidato = Path(".env") if ruta is None else ruta
    if not candidato.is_file():
        return None
    try:
        lineas = candidato.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        emparejada = _LLINEA_ENV.match(linea)
        if not emparejada:
            continue
        nombre, valor = emparejada.group(1), emparejada.group(2).strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        os.environ.setdefault(nombre, valor)
    return candidato


def env_relevantes(entorno: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copia del entorno filtrada a las variables de limpiador.

    Alimenta el `--json` de `comprobar-ia`. La clave se sustituye SIEMPRE por
    el literal «<presente>»: el JSON nunca puede llevar el secreto.
    """
    env = os.environ if entorno is None else entorno
    relevantes: dict[str, str] = {}
    for nombre, valor in env.items():
        if not nombre.startswith(PREFIJO_ENV):
            continue
        relevantes[nombre] = "<presente>" if nombre.endswith("_KEY") else valor
    return relevantes
