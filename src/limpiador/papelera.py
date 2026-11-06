"""Papelera de seguridad y reversión de operaciones (`limpiador deshacer`).

Por qué «borrar» seguro = mover a la papelera + manifiesto reversible:

1. Mover un fichero es una operación atómica que NO destruye datos: el
   contenido sigue intacto dentro de ``papelera/<marca-temporal>/``.
2. Cada ejecución real (`--si`) escribe un manifiesto JSON con el mapa
   exacto ``origen -> destino``. Con ese mapa, revertir es trivial:
   mover cada fichero de vuelta a su ruta original.
3. Si el borrado fuera definitivo (``unlink``), ningún manifiesto podría
   recuperar el contenido. Por eso la papelera es la forma segura de
   «borrar» y ``deshacer`` su contrapartida.

El manifiesto se guarda en ``<papelera>/.manifiesto/<op-id>.json`` con:
``op_id``, ``timestamp``, ``accion``, ``operacion``, ``carpeta_base``,
``entradas`` (lista de ``{origen, destino}``) y ``deshecha``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from limpiador.config import Accion, es_ruta_segura

CARPETA_PAPELERA_POR_DEFECTO: Final[str] = "papelera"
DIR_MANIFIESTO: Final[str] = ".manifiesto"
FORMATO_MARCA_TEMPORAL: Final[str] = "%Y%m%d-%H%M%S"


class PapeleraError(Exception):
    """Error al escribir o revertir un manifiesto de la papelera."""


@dataclass(frozen=True)
class EntradaManifiesto:
    """Un paso ejecutado: `origen` acabó en `destino` (None = borrado definitivo)."""

    origen: Path
    destino: Path | None


@dataclass(frozen=True)
class Manifiesto:
    """Operación real ya registrada en el fichero de la papelera."""

    op_id: str
    timestamp: str
    accion: str
    operacion: str
    carpeta_base: Path
    entradas: tuple[EntradaManifiesto, ...]
    deshecha: str | None
    ruta: Path


def base_papelera(accion: Accion, raiz: Path) -> Path:
    """Carpeta papelera de `accion` dentro de `raiz` (nunca fuera de ella).

    - ``papelera: true`` o ausente -> ``<raiz>/papelera``.
    - ``papelera: "DIR"``          -> ``<raiz>/DIR`` (DIR relativo y seguro).
    """
    if isinstance(accion.papelera, str) and accion.papelera:
        candidato = (raiz / accion.papelera).resolve()
        try:
            candidato.relative_to(raiz)
        except ValueError as exc:
            raise PapeleraError(
                f"la papelera '{accion.papelera}' queda fuera de la carpeta objetivo"
            ) from exc
        return candidato
    return raiz / CARPETA_PAPELERA_POR_DEFECTO


def nueva_marca_temporal() -> str:
    """Marca ``YYYYMMDD-HHMMSS`` para el subdirectorio de la papelera."""
    return datetime.now().strftime(FORMATO_MARCA_TEMPORAL)


def nuevo_op_id(marca: str) -> str:
    """Identificador único: marca temporal + sufijo aleatorio."""
    return f"{marca}-{uuid.uuid4().hex[:8]}"


def escribir_manifiesto(
    *,
    papelera_base: Path,
    op_id: str,
    accion: str,
    operacion: str,
    carpeta_base: Path,
    entradas: list[EntradaManifiesto],
    timestamp: str,
) -> Path:
    """Vuelca el manifiesto de la operación y devuelve su ruta."""
    ruta = papelera_base / DIR_MANIFIESTO / f"{op_id}.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    documento = {
        "op_id": op_id,
        "timestamp": timestamp,
        "accion": accion,
        "operacion": operacion,
        "carpeta_base": str(carpeta_base),
        "entradas": [
            {"origen": str(e.origen), "destino": str(e.destino) if e.destino else None}
            for e in entradas
        ],
        "deshecha": None,
    }
    ruta.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ruta


def _leer_manifiesto(ruta: Path) -> Manifiesto | None:
    """Parsea un manifiesto; devuelve None si no tiene la forma esperada."""
    try:
        datos: Any = json.loads(ruta.read_text(encoding="utf-8"))
        return Manifiesto(
            op_id=str(datos["op_id"]),
            timestamp=str(datos["timestamp"]),
            accion=str(datos["accion"]),
            operacion=str(datos.get("operacion", "")),
            carpeta_base=Path(str(datos["carpeta_base"])),
            entradas=tuple(
                EntradaManifiesto(
                    origen=Path(str(e["origen"])),
                    destino=Path(str(e["destino"])) if e.get("destino") is not None else None,
                )
                for e in datos["entradas"]
            ),
            deshecha=datos.get("deshecha"),
            ruta=ruta,
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def listar_manifiestos(papelera_base: Path) -> list[Manifiesto]:
    """Manifiestos pendientes de deshacer, del más reciente al más antiguo."""
    carpeta = papelera_base / DIR_MANIFIESTO
    if not carpeta.is_dir():
        return []
    manifiestos = [
        m
        for ruta in sorted(carpeta.glob("*.json"))
        if (m := _leer_manifiesto(ruta)) is not None and m.deshecha is None
    ]
    return sorted(manifiestos, key=lambda m: (m.timestamp, m.op_id), reverse=True)


def _ruta_restaurada(origen: Path) -> Path:
    """`nombre.restaurado.ext` cuando el original ya existe; con sufijo -N si hace falta."""
    candidato = origen.with_name(f"{origen.stem}.restaurado{origen.suffix}")
    if not candidato.exists():
        return candidato
    for i in range(1, 10_000):
        alternativo = origen.with_name(f"{origen.stem}.restaurado-{i}{origen.suffix}")
        if not alternativo.exists():
            return alternativo
    raise PapeleraError(f"demasiadas colisiones al restaurar '{origen.name}'")


def _esta_dentro(ruta: Path, raiz: Path) -> bool:
    """True si `ruta` queda dentro de `raiz` tras resolver enlaces."""
    try:
        ruta.resolve().relative_to(raiz)
    except ValueError:
        return False
    return True


def deshacer_operacion(papelera_base: Path, n: int = 1) -> tuple[Manifiesto, list[str]]:
    """Revierte la N-ésima operación más reciente. Devuelve bitácora de restauración.

    Lanza `PapeleraError` si no hay manifiesto, si la operación contiene
    borrados definitivos o si algo impide mover los ficheros de vuelta.
    """
    manifiestos = listar_manifiestos(papelera_base)
    if not manifiestos:
        raise PapeleraError(
            f"no hay operaciones pendientes de deshacer en '{papelera_base / DIR_MANIFIESTO}'"
        )
    if n > len(manifiestos):
        raise PapeleraError(
            f"solo hay {len(manifiestos)} operación(es) deshacible(s); "
            f"la número {n} no existe"
        )
    manifiesto = manifiestos[n - 1]
    if any(e.destino is None for e in manifiesto.entradas):
        raise PapeleraError(
            f"la operación '{manifiesto.op_id}' de la acción '{manifiesto.accion}' "
            "contiene borrados definitivos: no es reversible "
            "(activa 'papelera' en la acción para poder deshacer)"
        )

    raiz = manifiesto.carpeta_base
    bitacora: list[str] = []
    for entrada in reversed(manifiesto.entradas):
        destino, origen = entrada.destino, entrada.origen
        assert destino is not None  # comprobado arriba
        if not destino.is_file():
            raise PapeleraError(
                f"no se puede revertir '{origen.name}': '{destino}' ya no está en la papelera"
            )
        if not _esta_dentro(origen, raiz) or not _esta_dentro(destino, raiz):
            raise PapeleraError(
                f"el manifiesto '{manifiesto.op_id}' apunta fuera de '{raiz}': operación abortada"
            )
        destino_final = origen if not origen.exists() else _ruta_restaurada(origen)
        destino_final.parent.mkdir(parents=True, exist_ok=True)
        destino.replace(destino_final)
        if destino_final == origen:
            bitacora.append(f"restaurado {origen.name} -> {origen}")
        else:
            bitacora.append(
                f"AVISO: '{origen.name}' ya existía; restaurado como "
                f"'{destino_final.name}' (el original NO se ha sobreescrito)"
            )

    _marcar_como_deshecha(manifiesto)
    return manifiesto, bitacora


def _marcar_como_deshecha(manifiesto: Manifiesto) -> None:
    """Anota en el manifiesto que ya fue revertido (para no deshacer dos veces)."""
    try:
        datos = json.loads(manifiesto.ruta.read_text(encoding="utf-8"))
        datos["deshecha"] = datetime.now().isoformat(timespec="seconds")
        manifiesto.ruta.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, ValueError) as exc:  # pragma: no cover - disco inconsistente
        raise PapeleraError(f"no se pudo marcar el manifiesto: {exc}") from exc


def resolver_papelera_cli(carpeta: Path, papelera: str | None) -> Path:
    """Dir de papelera para `deshacer`: <carpeta>/papelera o <carpeta>/DIR.

    Rechaza path traversal (``..``) y rutas absolutas con `PapeleraError`.
    """
    if papelera is None:
        return carpeta / CARPETA_PAPELERA_POR_DEFECTO
    if not es_ruta_segura(papelera):
        raise PapeleraError(
            f"la papelera '{papelera}' no es una ruta relativa segura (sin '..', absolutas ni '~')"
        )
    return carpeta / papelera
