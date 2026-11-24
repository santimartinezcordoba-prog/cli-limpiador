"""Motor de las acciones: planificación (simulación) y ejecución real.

La planificación es pura: `planificar` solo mira el disco, no lo modifica.
`ejecutar` es la única función que escribe, y siempre dentro de la carpeta
objetivo, sin seguir enlaces simbólicos y sin borrar nunca la carpeta raíz.

Con la papelera activada, «borrar» se convierte en «mover a la papelera» y
cada ejecución real deja un manifiesto reversible en `<papelera>/.manifiesto/`
(ver `limpiador.papelera`).
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from limpiador.config import OPERACIONES_IA, Accion, Config
from limpiador.errores import AccionError
from limpiador.papelera import (
    EntradaManifiesto,
    base_papelera,
    escribir_manifiesto,
    nueva_marca_temporal,
    nuevo_op_id,
)


@dataclass(frozen=True)
class Operacion:
    """Un paso concreto: actuar sobre `origen` moviéndolo/renombrando a `destino`.

    Para las operaciones de fichero `destino` es un `Path`. Las acciones IA
    (`resumir-texto`, `clasificar-ficheros`) lo reutilizan para guardar una
    etiqueta legible (p. ej. `resumen/resumen-notas.md`), por eso es `Any`.
    """

    tipo: str
    origen: Path
    destino: Path | str | None = None

    @property
    def es_ia(self) -> bool:
        """True si la operación es IA: `destino` es etiqueta, no ruta a mover."""
        return self.tipo in OPERACIONES_IA

    @property
    def destino_path(self) -> Path:
        """`destino` como `Path` (solo para operaciones de fichero)."""
        assert isinstance(self.destino, Path)
        return self.destino

    @property
    def descripcion(self) -> str:
        if self.tipo == "borrar" and self.destino is None:
            return f"borrar {self.origen.name}"
        assert self.destino is not None
        # Acciones IA: `destino` es una etiqueta de salida, no una ruta a mover.
        if self.es_ia:
            return f"{self.tipo} {self.origen.name} -> {self.destino}"
        destino = self.destino_path
        if self.tipo in {"borrar", "dedup"}:  # destino dentro de la papelera
            ruta = "/".join(
                (destino.parent.parent.name, destino.parent.name, destino.name)
            )
            etiqueta = "borrar (papelera)" if self.tipo == "borrar" else "dedup (papelera)"
            return f"{etiqueta} {self.origen.name} -> {ruta}"
        carpeta = destino.parent.name
        return f"{self.tipo} {self.origen.name} -> {carpeta}/{destino.name}"


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
    return comprobar_carpeta_resuelta(carpeta)[1]


def comprobar_carpeta_resuelta(carpeta: Path) -> tuple[Path, Path]:
    """`(carpeta_original, resuelta)` validada; se reutiliza para no resolver dos veces."""
    if not carpeta.exists():
        raise AccionError(f"la carpeta '{carpeta}' no existe")
    if not carpeta.is_dir():
        raise AccionError(f"'{carpeta}' no es una carpeta")
    resuelta = carpeta.resolve()
    if resuelta == Path(resuelta.anchor):
        raise AccionError("se ha indicado la carpeta raíz del sistema; elige otra carpeta")
    return carpeta, resuelta


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


def ficheros_que_coinciden(accion: Accion, raiz: Path) -> list[Path]:
    """Ficheros de `raiz` que casan con los patrones de la acción.

    Reglas de seguridad:
    - solo ficheros (nunca carpetas, nunca la propia raíz),
    - se ignoran enlaces simbólicos (no los seguimos),
    - el resultado se deduplica y se ordena para que la salida sea determinista.
    """
    encontrados: set[Path] = set()
    patrones = [patron.casefold() for patron in accion.patrones]
    for coincidencia in raiz.iterdir():
        if coincidencia.is_symlink() or not coincidencia.is_file():
            continue
        if not _esta_dentro(coincidencia, raiz):
            continue
        if any(fnmatch.fnmatchcase(coincidencia.name.casefold(), p) for p in patrones):
            encontrados.add(coincidencia)
    return sorted(encontrados)


def _operaciones_a_papelera(
    tipo: str, origenes: list[Path], papelera_dir: Path
) -> list[Operacion]:
    """Plan de movimientos a `<papelera>/<marca-temporal>/` sin colisiones."""
    plan: list[Operacion] = []
    simulados: set[Path] = set()
    for origen in origenes:
        candidato = papelera_dir / origen.name
        if candidato.exists() or candidato in simulados:
            candidato = _destino_libre_simulado(candidato, simulados)
        simulados.add(candidato)
        plan.append(Operacion(tipo, origen, candidato))
    return plan


def _duplicados_sobrantes(objetivos: list[Path]) -> list[Path]:
    """De cada grupo de ficheros con el mismo SHA256, todos menos el primero."""
    grupos: dict[bytes, list[Path]] = {}
    for fichero in objetivos:
        try:
            digest = hashlib.sha256(fichero.read_bytes()).digest()
        except OSError as exc:
            raise AccionError(f"no se pudo leer '{fichero.name}' para dedup: {exc}") from exc
        grupos.setdefault(digest, []).append(fichero)
    sobrantes = [fichero for lista in grupos.values() for fichero in lista[1:]]
    return sorted(sobrantes)


def planificar(accion: Accion, carpeta: Path) -> list[Operacion]:
    """Calcula qué haría la acción sin tocar nada (modo `--simular`)."""
    _, raiz = comprobar_carpeta_resuelta(carpeta)
    objetivos = ficheros_que_coinciden(accion, raiz)
    return planificar_desde_objetivos(accion, raiz, objetivos)


class AccionPlanificadora(ABC):
    """Acción de dominio creada a partir de una configuración validada."""

    def __init__(self, config: Accion) -> None:
        self.config = config

    @staticmethod
    def desde_config(config: Accion) -> AccionPlanificadora:
        """Selecciona el planificador que corresponde a la operación."""
        tipos: dict[str, type[AccionPlanificadora]] = {
            "mover": Mover, "borrar": Borrar, "renombrar": Renombrar,
            "dedup": Deduplicar, "resumir-texto": AccionIA,
            "clasificar-ficheros": AccionIA,
        }
        try:
            return tipos[config.operacion](config)
        except KeyError as exc:
            raise AccionError(f"operación desconocida: {config.operacion}") from exc

    @abstractmethod
    def planificar(self, raiz: Path, objetivos: list[Path]) -> list[Operacion]:
        """Crea un plan sin modificar el disco."""


class AccionIA(AccionPlanificadora):
    def planificar(self, raiz: Path, objetivos: list[Path]) -> list[Operacion]:
        from limpiador import acciones_ia
        return acciones_ia.planificar_ia(self.config, raiz, objetivos)


class Borrar(AccionPlanificadora):
    def planificar(self, raiz: Path, objetivos: list[Path]) -> list[Operacion]:
        if self.config.papelera:
            papelera = base_papelera(self.config, raiz) / nueva_marca_temporal()
            return _operaciones_a_papelera("borrar", objetivos, papelera)
        return [Operacion("borrar", origen) for origen in objetivos]


class Deduplicar(AccionPlanificadora):
    def planificar(self, raiz: Path, objetivos: list[Path]) -> list[Operacion]:
        papelera = base_papelera(self.config, raiz) / nueva_marca_temporal()
        return _operaciones_a_papelera("dedup", _duplicados_sobrantes(objetivos), papelera)


class Mover(AccionPlanificadora):
    def planificar(self, raiz: Path, objetivos: list[Path]) -> list[Operacion]:
        assert self.config.destino is not None
        destino_dir = _dentro_seguro(self.config.destino, raiz)
        plan: list[Operacion] = []
        simulados: set[Path] = set()
        for origen in objetivos:
            if destino_dir.exists() and origen.parent == destino_dir:
                continue
            candidato = destino_dir / origen.name
            if candidato.exists() or candidato in simulados:
                candidato = _destino_libre_simulado(candidato, simulados)
            simulados.add(candidato)
            plan.append(Operacion("mover", origen, candidato))
        return plan


class Renombrar(AccionPlanificadora):
    def planificar(self, raiz: Path, objetivos: list[Path]) -> list[Operacion]:
        assert self.config.sufijo is not None
        plan: list[Operacion] = []
        simulados: set[Path] = set()
        for origen in objetivos:
            sufijo = re.escape(self.config.sufijo)
            if re.search(rf"-{sufijo}(?:-\d+)?$", origen.stem):
                continue
            nuevo = origen.with_name(f"{origen.stem}-{self.config.sufijo}{origen.suffix}")
            if nuevo.exists() or nuevo in simulados:
                nuevo = _destino_libre_simulado(nuevo, simulados)
            simulados.add(nuevo)
            plan.append(Operacion("renombrar", origen, nuevo))
        return plan


def planificar_desde_objetivos(
    accion: Accion, raiz: Path, objetivos: list[Path]
) -> list[Operacion]:
    """Planifica con la carpeta ya validada y los objetivos contados."""
    return AccionPlanificadora.desde_config(accion).planificar(raiz, objetivos)


def _destino_libre_simulado(destino: Path, ya_planificados: set[Path]) -> Path:
    """Versión de `_destino_libre` que también respeta nombres del propio plan."""
    base, sufijo, padre = destino.stem, destino.suffix, destino.parent
    for i in range(1, 10_000):
        alternativo = padre / f"{base}-{i}{sufijo}"
        if not alternativo.exists() and alternativo not in ya_planificados:
            return alternativo
    raise AccionError(f"demasiadas colisiones de nombre para '{destino.name}'")


def ejecutar(
    accion: Accion, carpeta: Path, plan: list[Operacion]
) -> tuple[list[str], Path | None]:
    """Aplica el plan calculado por `planificar`.

    Devuelve (bitácora, ruta_del_manifiesto). El manifiesto se escribe en
    `<papelera>/.manifiesto/<op-id>.json` en cada ejecución real (`--si`) y
    permite revertirla con `limpiador deshacer`. Lanza `AccionError` si alguna
    operación no es segura (fuera de la raíz).
    """
    raiz = _comprobar_carpeta(carpeta)
    papelera_base = base_papelera(accion, raiz)
    bitacora: list[str] = []
    entradas: list[EntradaManifiesto] = []
    if plan and all(operacion.es_ia for operacion in plan):
        # Las acciones IA no tienen plan que aplicar: quien escribe es
        # `acciones_ia.ejecutar_*` (llamado desde la CLI). Llegar aquí por
        # accidente usaría `destino` (una etiqueta) como ruta: se corta.
        raise AccionError(
            "las acciones IA se ejecutan con el motor de IA, no con el plan"
        )
    for operacion in plan:
        if not _esta_dentro(operacion.origen, raiz):
            raise AccionError(f"'{operacion.origen}' queda fuera de '{raiz}'")
        if (
            isinstance(operacion.destino, Path)
            and not _esta_dentro(operacion.destino, raiz)
        ):
            raise AccionError(f"el destino '{operacion.destino}' queda fuera de '{raiz}'")

        if operacion.tipo == "borrar" and operacion.destino is None:
            operacion.origen.unlink()
            bitacora.append(f"borrado {operacion.origen.name}")
            entradas.append(EntradaManifiesto(operacion.origen, None))
        elif operacion.tipo in {"borrar", "dedup"}:
            # Borrar con papelera / dedup: mover en vez de destruir.
            destino_previsto = operacion.destino_path
            destino_previsto.parent.mkdir(parents=True, exist_ok=True)
            destino_final = _destino_libre(destino_previsto)
            operacion.origen.replace(destino_final)
            etiqueta = "a papelera" if operacion.tipo == "borrar" else "duplicado a papelera"
            bitacora.append(
                f"{operacion.origen.name} {etiqueta} -> "
                f"{destino_final.parent.name}/{destino_final.name}"
            )
            entradas.append(EntradaManifiesto(operacion.origen, destino_final))
        elif operacion.tipo == "mover":
            destino_previsto = operacion.destino_path
            destino_previsto.parent.mkdir(parents=True, exist_ok=True)
            destino_final = _destino_libre(destino_previsto)
            operacion.origen.replace(destino_final)
            bitacora.append(
                f"movido {operacion.origen.name} -> "
                f"{destino_final.parent.name}/{destino_final.name}"
            )
            entradas.append(EntradaManifiesto(operacion.origen, destino_final))
        elif operacion.tipo == "renombrar":
            destino_final = _destino_libre(operacion.destino_path)
            operacion.origen.replace(destino_final)
            bitacora.append(f"renombrado {operacion.origen.name} -> {destino_final.name}")
            entradas.append(EntradaManifiesto(operacion.origen, destino_final))
        else:  # pragma: no cover - imposible tras la validación
            raise AccionError(f"operación desconocida: {operacion.tipo}")

    if not entradas:
        return bitacora, None
    manifiesto = escribir_manifiesto(
        papelera_base=papelera_base,
        op_id=nuevo_op_id(nueva_marca_temporal()),
        accion=accion.nombre,
        operacion=accion.operacion,
        carpeta_base=raiz,
        entradas=entradas,
        timestamp=datetime.now().isoformat(timespec="microseconds"),
    )
    return bitacora, manifiesto


class Motor:
    """Planifica y ejecuta acciones sin depender de la interfaz de consola."""

    def planificar(self, accion: Accion, carpeta: Path) -> list[Operacion]:
        return planificar(accion, carpeta)

    def ejecutar(
        self, accion: Accion, carpeta: Path, plan: list[Operacion]
    ) -> tuple[list[str], Path | None]:
        return ejecutar(accion, carpeta, plan)
