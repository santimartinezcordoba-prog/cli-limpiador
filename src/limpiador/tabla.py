"""Construcción de las tablas Rich que muestra la CLI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.table import Table
from rich.text import Text

from limpiador.acciones import Operacion
from limpiador.config import Accion


def _tamaño_legible(bytes_: int) -> str:
    """Formatea un tamaño en bytes de forma legible (ej. ``1.4 KB``)."""
    tam = float(bytes_)
    for unidad in ("B", "KB", "MB", "GB", "TB"):
        if tam < 1024 or unidad == "TB":
            texto = f"{tam:.0f} {unidad}" if unidad == "B" else f"{tam:.1f} {unidad}"
            return texto
        tam /= 1024
    return f"{tam:.1f} TB"  # pragma: no cover


def _nombre(nombre: str) -> Text:
    """Celda de Rich para un nombre (evita interpretar corchetes como markup)."""
    return Text(nombre)


def tabla_ficheros(carpeta: Path, ficheros: list[Path]) -> Table:
    """Tabla con nombre, tipo, tamaño y fecha de modificación."""
    tabla = Table(title=f"Contenido de {carpeta}", title_style="bold cyan")
    tabla.add_column("Nombre", overflow="fold")
    tabla.add_column("Tipo", justify="left")
    tabla.add_column("Tamaño", justify="right")
    tabla.add_column("Modificado", justify="left")
    for fichero in ficheros:
        enlace = fichero.is_symlink()
        # lstat() evita seguir el enlace: funciona incluso con enlaces rotos.
        stat = fichero.lstat() if enlace else fichero.stat()
        tabla.add_row(
            _nombre(fichero.name),
            "enlace" if enlace else "fichero",
            _tamaño_legible(stat.st_size),
            datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        )
    return tabla


def tabla_acciones(config_version: int, acciones: list[Accion]) -> Table:
    """Tabla resumen de las acciones del fichero de configuración."""
    tabla = Table(
        title=f"Acciones definidas (config v{config_version})", title_style="bold cyan"
    )
    tabla.add_column("Nombre", style="bold")
    tabla.add_column("Operación")
    tabla.add_column("Patrones", overflow="fold")
    tabla.add_column("Descripción", overflow="fold")
    for accion in acciones:
        tabla.add_row(
            accion.nombre,
            accion.operacion,
            ", ".join(accion.patrones),
            accion.descripcion,
        )
    return tabla


def tabla_operaciones(plan: list[Operacion], simulacion: bool) -> Table:
    """Tabla de pasos que la acción daría (simulación) o va a ejecutar."""
    if simulacion:
        rotulo, color = "Pasos que daría (SIMULACIÓN)", "bold yellow"
    else:
        rotulo, color = "Pasos a ejecutar", "bold green"
    tabla = Table(title=rotulo, title_style=color)
    tabla.add_column("#", justify="right")
    tabla.add_column("Paso")
    for i, operacion in enumerate(plan, start=1):
        tabla.add_row(str(i), Text(operacion.descripcion))
    return tabla
