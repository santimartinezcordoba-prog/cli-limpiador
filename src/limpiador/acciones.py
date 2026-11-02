"""Motor de las acciones: planificación (simulación) y ejecución real.

La planificación es pura: `planificar` solo mira el disco, no lo modifica.
`ejecutar` es la única función que escribe, y siempre dentro de la carpeta
objetivo, sin seguir enlaces simbólicos y sin borrar nunca la carpeta raíz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from limpiador.config import Accion, Config


class AccionError(Exception):
    """Error al resolver o ejecutar una acción (carpeta, colisiones, permisos)."""


@dataclass(frozen=True)
class Operacion:
    """Un paso concreto: actuar sobre `origen` moviéndolo/renombrando a `destino`."""

    tipo: str
    origen: Path
    destino: Path | None = None

    @property
    def descripcion(self) -> str:
        if self.tipo == "borrar":
            return f"borrar {self.origen.name}"
        assert self.destino is not None
        carpeta = self.destino.parent.name
        return f"{self.tipo} {self.origen.name} -> {carpeta}/{self.destino.name}"


def buscar_accion(config: Config, nombre: str) -> Accion:
    """Devuelve la acción llamada `nombre` o lanza `AccionError` con alternativas."""
    for accion in config.acciones:
        if accion.nombre == nombre:
            return accion
    disponibles = ", ".join(a.nombre for a in config.acciones)
    raise AccionError(
        f"no existe la acción '{nombre}'. Acciones disponibles: {disponibles}"
    )


def _comprobar_carpeta(carpeta: Path) -> Path:
    """Resuelve y valida la carpeta objetivo. Nunca devuelve la raíz del sistema."""
    if not carpeta.exists():
        raise AccionError(f"la carpeta '{carpeta}' no existe")
    if not carpeta.is_dir():
        raise AccionError(f"'{carpeta}' no es una carpeta")
    resuelta = carpeta.resolve()
    if resuelta == Path(resuelta.anchor):
        raise AccionError("se ha indicado la carpeta raíz del sistema; elige otra carpeta")
    return resuelta


def _esta_dentro(ruta: Path, raiz: Path) -> bool:
    """True si `ruta` queda dentro de `raiz` tras resolver enlaces."""
    try:
        ruta.resolve().relative_to(raiz)
    except ValueError:
        return False
    return True


def _dentro_seguro(nombre: str, raiz: Path) -> Path:
    """Construye `raiz/nombre` verificando que no se sale de `raiz`.

    Si el directorio existe como enlace simbólico apuntando fuera,
    `resolve()` lo delata y lo rechazamos.
    """
    candidato = raiz / nombre
    if not _esta_dentro(candidato, raiz):
        raise AccionError(f"la ruta '{nombre}' queda fuera de la carpeta objetivo")
    return candidato


def _destino_libre(destino: Path) -> Path:
    """Evita sobrescribir: si el destino existe, añade -1, -2, ... al nombre."""
    if not destino.exists():
        return destino
    base, sufijo, padre = destino.stem, destino.suffix, destino.parent
    for i in range(1, 10_000):
        alternativo = padre / f"{base}-{i}{sufijo}"
        if not alternativo.exists():
            return alternativo
    raise AccionError(f"demasiadas colisiones de nombre para '{destino.name}'")


def _ficheros_que_coinciden(accion: Accion, raiz: Path) -> list[Path]:
    """Ficheros de `raiz` que casan con los patrones de la acción.

    Reglas de seguridad:
    - solo ficheros (nunca carpetas, nunca la propia raíz),
    - se ignoran enlaces simbólicos (no los seguimos),
    - el resultado se deduplica y se ordena para que la salida sea determinista.
    """
    encontrados: set[Path] = set()
    for patron in accion.patrones:
        for coincidencia in raiz.glob(patron):
            if coincidencia.is_symlink():
                continue
            if not coincidencia.is_file():
                continue
            if not _esta_dentro(coincidencia, raiz):
                continue
            encontrados.add(coincidencia)
    return sorted(encontrados)


def planificar(accion: Accion, carpeta: Path) -> list[Operacion]:
    """Calcula qué haría la acción sin tocar nada (modo `--simular`)."""
    raiz = _comprobar_carpeta(carpeta)
    objetivos = _ficheros_que_coinciden(accion, raiz)

    if accion.operacion == "borrar":
        return [Operacion("borrar", origen) for origen in objetivos]

    if accion.operacion == "mover":
        assert accion.destino is not None  # garantizado por la validación
        destino_dir = _dentro_seguro(accion.destino, raiz)
        plan: list[Operacion] = []
        simulo_existente: set[Path] = set()
        for origen in objetivos:
            if destino_dir.exists() and origen.parent == destino_dir:
                continue  # ya está en su sitio
            candidato = destino_dir / origen.name
            if candidato.exists() or candidato in simulo_existente:
                candidato = _destino_libre_simulado(candidato, simulo_existente)
            simulo_existente.add(candidato)
            plan.append(Operacion("mover", origen, candidato))
        return plan

    # renombrar: añade `sufijo` antes de la extensión, en la misma carpeta.
    assert accion.sufijo is not None  # garantizado por la validación
    plan = []
    simulados: set[Path] = set()
    for origen in objetivos:
        nuevo = origen.with_name(f"{origen.stem}-{accion.sufijo}{origen.suffix}")
        if nuevo.exists() or nuevo in simulados:
            nuevo = _destino_libre_simulado(nuevo, simulados)
        simulados.add(nuevo)
        plan.append(Operacion("renombrar", origen, nuevo))
    return plan


def _destino_libre_simulado(destino: Path, ya_planificados: set[Path]) -> Path:
    """Versión de `_destino_libre` que también respeta nombres del propio plan."""
    base, sufijo, padre = destino.stem, destino.suffix, destino.parent
    for i in range(1, 10_000):
        alternativo = padre / f"{base}-{i}{sufijo}"
        if not alternativo.exists() and alternativo not in ya_planificados:
            return alternativo
    raise AccionError(f"demasiadas colisiones de nombre para '{destino.name}'")


def ejecutar(accion: Accion, carpeta: Path, plan: list[Operacion]) -> list[str]:
    """Aplica el plan calculado por `planificar`. Devuelve líneas de progreso.

    Lanza `AccionError` si alguna operación no es segura (fuera de la raíz).
    """
    raiz = _comprobar_carpeta(carpeta)
    bitacora: list[str] = []
    for operacion in plan:
        if not _esta_dentro(operacion.origen, raiz):
            raise AccionError(f"'{operacion.origen}' queda fuera de '{raiz}'")
        if operacion.destino is not None and not _esta_dentro(operacion.destino, raiz):
            raise AccionError(f"el destino '{operacion.destino}' queda fuera de '{raiz}'")

        if operacion.tipo == "borrar":
            operacion.origen.unlink()
            bitacora.append(f"borrado {operacion.origen.name}")
        elif operacion.tipo == "mover":
            assert operacion.destino is not None
            operacion.destino.parent.mkdir(parents=True, exist_ok=True)
            destino_final = _destino_libre(operacion.destino)
            operacion.origen.replace(destino_final)
            bitacora.append(
                f"movido {operacion.origen.name} -> "
                f"{destino_final.parent.name}/{destino_final.name}"
            )
        elif operacion.tipo == "renombrar":
            assert operacion.destino is not None
            destino_final = _destino_libre(operacion.destino)
            operacion.origen.replace(destino_final)
            bitacora.append(f"renombrado {operacion.origen.name} -> {destino_final.name}")
        else:  # pragma: no cover - imposible tras la validación
            raise AccionError(f"operación desconocida: {operacion.tipo}")
    return bitacora
