"""Carga y validación del fichero de acciones (`acciones.json`) con pydantic.

Toda la validación se hace «en seco»: nunca se toca el disco más allá de
leer el propio JSON. Los modelos `Accion` y `Config` de pydantic comprueban
tipos, campos obligatorios y coherencia entre campos; los errores se mapean a
mensajes propios con la ruta exacta del campo, del estilo
``acciones[0].nombre: campo requerido``, y se acumulan TODOS de golpe (no
solo el primero).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)

# Whitlist de operaciones ejecutables. El orden importa: se muestra tal cual
# en el mensaje «valor no soportado (permitido: mover, borrar, ...)».
OPERACIONES_VALIDAS: Final[tuple[str, ...]] = ("mover", "borrar", "renombrar", "dedup")

LISTA_OPERACIONES: Final[str] = ", ".join(OPERACIONES_VALIDAS)

# Campos admitidos en cada acción (los extra se rechazan con extra="forbid").
CAMPOS_ACEPTADOS: Final[frozenset[str]] = frozenset(
    {"nombre", "descripcion", "operacion", "patrones", "destino", "sufijo", "papelera"}
)

# Operaciones para las que tiene sentido activar la papelera.
OPERACIONES_CON_PAPELERA: Final[frozenset[str]] = frozenset({"borrar", "dedup"})


class ConfigInvalidaError(Exception):
    """Error de configuración que arrastra la lista completa de fallos."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = errores
        super().__init__("; ".join(errores))


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

    @field_validator("operacion")
    @classmethod
    def _operacion_en_whitelist(cls, valor: str) -> str:
        if valor not in OPERACIONES_VALIDAS:
            raise ValueError(f"valor no soportado (permitido: {LISTA_OPERACIONES})")
        return valor

    @field_validator("papelera")
    @classmethod
    def _papelera_coherente(
        cls, valor: bool | str | None, info: ValidationInfo
    ) -> bool | str | None:
        if isinstance(valor, str):
            if not valor:
                raise ValueError("debe ser un texto no vacío")
            if not es_ruta_segura(valor):
                raise ValueError("debe ser una ruta relativa segura")
        operacion = info.data.get("operacion")
        if (
            operacion is not None
            and valor is not None
            and operacion not in OPERACIONES_CON_PAPELERA
        ):
            raise ValueError("solo aplica a las operaciones 'borrar' o 'dedup'")
        return valor

    @field_validator("destino")
    @classmethod
    def _destino_coherente(cls, valor: str | None, info: ValidationInfo) -> str | None:
        operacion = info.data.get("operacion")
        if operacion is None:
            return valor  # 'operacion' ya ha fallado: no duplicamos culpas.
        if operacion == "mover":
            if valor is None:
                raise ValueError(
                    "campo requerido ('destino' es obligatorio "
                    "cuando operacion='mover')"
                )
            if not es_ruta_segura(valor):
                raise ValueError("debe ser una ruta relativa segura")
        elif valor is not None:
            raise ValueError("solo aplica a la operación 'mover'")
        return valor

    @field_validator("sufijo")
    @classmethod
    def _sufijo_coherente(cls, valor: str | None, info: ValidationInfo) -> str | None:
        operacion = info.data.get("operacion")
        if operacion is None:
            return valor
        if operacion == "renombrar":
            if valor is None:
                raise ValueError(
                    "campo requerido ('sufijo' es obligatorio "
                    "cuando operacion='renombrar')"
                )
            if "/" in valor or "\\" in valor or ".." in valor:
                raise ValueError("no puede contener rutas")
        elif valor is not None:
            raise ValueError("solo aplica a la operación 'renombrar'")
        return valor


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
    if not isinstance(datos, dict):
        raise ConfigInvalidaError(["<raíz>: el fichero debe ser un objeto JSON"])

    try:
        config = Config.model_validate(datos)
        errores: list[str] = []
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
