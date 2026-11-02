"""limpiador: CLI para limpiar y ordenar ficheros con un fichero de acciones JSON."""

from importlib import metadata

try:
    # La versión real es la del paquete instalado (pyproject.toml).
    __version__ = metadata.version("limpiador")
except metadata.PackageNotFoundError:  # pragma: no cover
    # Solo ocurre si se ejecuta sin instalar el paquete.
    __version__ = "0.0.0"

__all__ = ["__version__"]
