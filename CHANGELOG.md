# Changelog

Todas las diferencias notables en este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/),
y el proyecto admite [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

## [1.0.0] - 2026-11-02

### Añadido

- Primera versión pública de la CLI `limpiador`.
- `limpiador version`: muestra la versión instalada.
- `limpiador listar [CARPETA]`: tabla Rich con nombre, tipo, tamaño y fecha
  de cada fichero (solo lectura).
- `limpiador acciones`: lista las acciones definidas en `acciones.json`.
- `limpiador validar`: valida la configuración y reporta el campo exacto que
  falla (`acciones[i].campo: motivo`) con exit code `3` si es inválida.
- `limpiador ejecutar NOMBRE [CARPETA]`:
  - `--simular` muestra el plan sin tocar el disco,
  - `--si` ejecuta sin preguntar (para scripts),
  - sin flags pide confirmación interactiva; sin TTY se niega y sale con `2`.
- Opción global `--config RUTA` para usar otro fichero de acciones.
- Operaciones soportadas: `mover`, `borrar` y `renombrar`.
- Seguridad: sin path traversal, sin seguir enlaces simbólicos, sin
  sobrescribir ficheros y sin actuar fuera de la carpeta objetivo.
- Suite de pruebas con pytest sobre carpetas temporales (`tmp_path`).
- CI con GitHub Actions (ruff, mypy, pytest, humo de instalación) en Python
  3.10, 3.11 y 3.12.

[unreleased]: https://github.com/TU_USUARIO/cli-limpiador/compare/v1.0...HEAD
[1.0.0]: https://github.com/TU_USUARIO/cli-limpiador/releases/tag/v1.0
