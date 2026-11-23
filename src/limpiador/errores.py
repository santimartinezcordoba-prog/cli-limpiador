"""Códigos de salida de la CLI `limpiador` (contrato único, estable).

Se centralizan aquí (en lugar de repetir literales por el código) para que el
contrato de *exit codes* sea una sola fuente de verdad, compartida por el
motor (`acciones.py`, `ia.py`) y la interfaz (`cli.py`). Así el motor es
testeable sin Typer: devuelve estos códigos sin importar `typer`.

- `0` `EXIT_OK`             : todo correcto.
- `1` `EXIT_ERROR`          : error de uso en tiempo de ejecución (acción o
                              carpeta inexistente, `deshacer` sin manifiesto).
- `2` `EXIT_SIN_CONFIRMAR`  : falta confirmación (sin TTY y sin `--si`) o
                              flags incompatibles.
- `3` `EXIT_CONFIG_INVALIDA`: el fichero de configuración no es válido. En
                              `comprobar-ia` reutiliza el 3 para «sin API key».
- `4` `EXIT_OFFLINE`        : completado en modo degradado/sin red. La acción
                              IA terminó usando heurística local porque no
                              había key o porque falló la conexión (timeout,
                              503, fallo de red). No es un fallo: el trabajo
                              salió, pero sin la IA del centro.
"""

from __future__ import annotations

from typing import Final

EXIT_OK: Final = 0
EXIT_ERROR: Final = 1
EXIT_SIN_CONFIRMAR: Final = 2
EXIT_CONFIG_INVALIDA: Final = 3
EXIT_OFFLINE: Final = 4

__all__ = [
    "EXIT_OK",
    "EXIT_ERROR",
    "EXIT_SIN_CONFIRMAR",
    "EXIT_CONFIG_INVALIDA",
    "EXIT_OFFLINE",
]
