"""Carga y validación del fichero de acciones (`acciones.json`).

Toda la validación se hace «en seco»: nunca se toca el disco más allá de
leer el propio JSON. Los errores se acumulan en una lista con rutas exactas
del estilo ``acciones[0].nombre: campo requerido``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

OPERACIONES_VALIDAS: Final[frozenset[str]] = frozenset({"mover", "borrar", "renombrar"})

CAMPOS_ACEPTADOS: Final[frozenset[str]] = frozenset(
    {"nombre", "descripcion", "operacion", "patrones", "destino", "sufijo"}
)


class ConfigInvalidaError(Exception):
    """Error de configuración que arrastra la lista completa de fallos."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = errores
        super().__init__("; ".join(errores))


@dataclass(frozen=True)
class Accion:
    """Una acción ya validada, lista para ejecutarse."""

    nombre: str
    descripcion: str
    operacion: str
    patrones: tuple[str, ...]
    destino: str | None = None
    sufijo: str | None = None


@dataclass
class Config:
    """Configuración completa del fichero de acciones."""

    version: int
    acciones: list[Accion] = field(default_factory=list)


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


def _texto_requerido(
    datos: dict[str, Any], clave: str, prefijo: str, errores: list[str]
) -> str | None:
    """Devuelve el texto de `clave` o registra el error correspondiente."""
    valor = datos.get(clave)
    if valor is None:
        errores.append(f"{prefijo}.{clave}: campo requerido")
        return None
    if not isinstance(valor, str) or not valor.strip():
        errores.append(f"{prefijo}.{clave}: debe ser un texto no vacío")
        return None
    return valor.strip()


def _validar_accion(indice: int, datos: Any, errores: list[str]) -> Accion | None:
    """Valida una acción suelta; añade cada fallo a `errores`.

    Devuelve la `Accion` construida solo si esta acción no tiene ningún error.
    """
    prefijo = f"acciones[{indice}]"
    if not isinstance(datos, dict):
        errores.append(f"{prefijo}: debe ser un objeto JSON")
        return None

    for clave_ajena in sorted(set(datos) - CAMPOS_ACEPTADOS):
        errores.append(f"{prefijo}.{clave_ajena}: campo no permitido")

    nombre = _texto_requerido(datos, "nombre", prefijo, errores)
    descripcion = _texto_requerido(datos, "descripcion", prefijo, errores)

    operacion = datos.get("operacion")
    if operacion is None:
        errores.append(f"{prefijo}.operacion: campo requerido")
        operacion = None
    elif not isinstance(operacion, str) or operacion not in OPERACIONES_VALIDAS:
        errores.append(f"{prefijo}.operacion: valor no soportado")
        operacion = None

    patrones = datos.get("patrones")
    patrones_ok: tuple[str, ...] = ()
    if patrones is None:
        errores.append(f"{prefijo}.patrones: campo requerido")
    elif not isinstance(patrones, list) or not patrones:
        errores.append(f"{prefijo}.patrones: debe ser una lista con al menos un patrón")
    else:
        invalidos = [
            f"{prefijo}.patrones[{i}]: patrón inválido o no seguro"
            for i, p in enumerate(patrones)
            if not isinstance(p, str) or not es_patron_seguro(p)
        ]
        errores.extend(invalidos)
        if not invalidos:
            patrones_ok = tuple(p for p in patrones if isinstance(p, str))

    destino = datos.get("destino")
    destino_ok: str | None = None
    if operacion == "mover":
        if destino is None:
            errores.append(f"{prefijo}.destino: campo requerido")
        elif not isinstance(destino, str) or not es_ruta_segura(destino):
            errores.append(f"{prefijo}.destino: debe ser una ruta relativa segura")
        else:
            destino_ok = destino
    elif destino is not None:
        errores.append(f"{prefijo}.destino: solo aplica a la operación 'mover'")

    sufijo = datos.get("sufijo")
    sufijo_ok: str | None = None
    if operacion == "renombrar":
        if sufijo is None:
            errores.append(f"{prefijo}.sufijo: campo requerido")
        elif not isinstance(sufijo, str) or not sufijo.strip():
            errores.append(f"{prefijo}.sufijo: debe ser un texto no vacío")
        elif "/" in sufijo or "\\" in sufijo or ".." in sufijo:
            errores.append(f"{prefijo}.sufijo: no puede contener rutas")
        else:
            sufijo_ok = sufijo.strip()
    elif sufijo is not None:
        errores.append(f"{prefijo}.sufijo: solo aplica a la operación 'renombrar'")

    if errores or nombre is None or descripcion is None or operacion is None or not patrones_ok:
        return None
    return Accion(
        nombre=nombre,
        descripcion=descripcion,
        operacion=operacion,
        patrones=patrones_ok,
        destino=destino_ok,
        sufijo=sufijo_ok,
    )


def validar_contenido(datos: Any) -> Config:
    """Valida el JSON ya parseado y lanza `ConfigInvalidaError` si algo falla."""
    errores: list[str] = []

    if not isinstance(datos, dict):
        raise ConfigInvalidaError(["<raíz>: el fichero debe ser un objeto JSON"])

    version = datos.get("version", 1)
    if not isinstance(version, int) or isinstance(version, bool):
        errores.append("<raíz>.version: debe ser un entero")
        version = 1

    if "acciones" not in datos:
        errores.append("<raíz>.acciones: campo requerido")
        raise ConfigInvalidaError(errores)

    lista = datos["acciones"]
    if not isinstance(lista, list) or not lista:
        raise ConfigInvalidaError(
            ["<raíz>.acciones: debe ser una lista con al menos una acción"]
        )

    acciones: list[Accion] = []
    nombres_vistos: set[str] = set()
    for i, item in enumerate(lista):
        # Cada acción se valida con su propia lista de errores para poder
        # seguir comprobando el resto y reportar todos los fallos a la vez.
        errores_accion: list[str] = []
        accion = _validar_accion(i, item, errores_accion)
        errores.extend(errores_accion)
        if accion is not None:
            if accion.nombre in nombres_vistos:
                errores.append(f"acciones[{i}].nombre: nombre duplicado '{accion.nombre}'")
            nombres_vistos.add(accion.nombre)
            acciones.append(accion)

    if errores:
        raise ConfigInvalidaError(errores)
    return Config(version=version, acciones=acciones)


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
                f"{ruta}: JSON mal formado en la línea {exc.lineno}, "
                f"columna {exc.colno}: {exc.msg}"
            ]
        ) from exc
    return validar_contenido(datos)
