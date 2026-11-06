# Changelog

Todas las diferencias notables en este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/),
y el proyecto admite [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

## [1.1.0] - 2026-11-06

### Añadido

- Papelera de seguridad: campo opcional `"papelera": true | "DIR"` en acciones
  `borrar`/`dedup`. El borrado «seguro» mueve a
  `<carpeta>/papelera/<YYYYMMDD-HHMMSS>/<nombre>` dentro de la carpeta
  objetivo y escribe un manifiesto reversible en
  `<papelera>/.manifiesto/<op-id>.json` (`op_id`, `timestamp`, `accion`,
  `carpeta_base`, entradas `{origen, destino}`) en toda ejecución real `--si`.
- `limpiador deshacer [N] [--carpeta] [--papelera]`: revierte la N-ésima
  ejecución más reciente devolviendo cada fichero a su ruta original; si el
  original existe, crea `nombre.restaurado.ext` sin sobrescribir. Exit `1`
  sin manifiesto o con borrados definitivos no reversibles.
- Operación `dedup` en la whitelist: los duplicados por SHA256 viajan siempre
  a la papelera (reversible con `deshacer`).
- `limpiador validar --json`: resultado estructurado (`valido`, `errores[]`)
  para scripts y auditorías.
- `limpiador doctor`: diagnóstico del entorno (Python + typer/rich/pydantic);
  sale `0` si la instalación es usable.
- CI `install-smoke`: en entorno limpio (ubuntu + Python 3.12) instala con
  `uv tool install .` (fallback `pipx`) y verifica `version`, `doctor` y que
  `--help` lista todas las órdenes, incluida `deshacer`.
- CI `os-matrix`: pytest en ubuntu, macOS y windows (Python 3.12).
- Prueba de hash: helper `tree_hash(dir)` (SHA256 de rutas+contenidos) y
  `test_simular_no_toca_disco_hash_identico` parametrizado por operación:
  demuestra empíricamente que `--simular` no escribe ni un byte.
- README: secciones «Auditoría de tests» (tabla Test/Qué aserta/Por qué
  importa), «Seguridad: amenazas y mitigaciones», «Papelera y deshacer» y
  «Uso end-to-end» (init → validar → simular → si → deshacer).

### Cambiado

- `config.py` reescrito con modelos pydantic (`Accion` + `Config`); los
  errores de validación conservan el contrato `acciones[i].campo: motivo` y
  amplían mensajes: `valor no soportado (permitido: mover, borrar, renombrar,
  dedup)` y `'destino' es obligatorio cuando operacion='mover'`.
- Mensaje de JSON corrupto: «JSON inválido: mal formado en la línea N…».
- La whitelist de operaciones incluye `dedup` (antes: mover, borrar, renombrar).
- `ejecutar --si` imprime la ruta del manifiesto e invita a `deshacer`.

## [1.0.1] - 2026-11-03

### Corregido

- Pruebas: las comparaciones de la salida de la CLI se normalizan (se
  eliminan los códigos ANSI de Rich) para que los `assert` por substring no
  dependan de la terminal del entorno. Esto arreglaba un fallo intermitente
  de CI (`test_ayuda_enumera_todas_las_ordenes`) con versiones recientes de
  Rich, que emitía escapes pese a `NO_COLOR`.
- README: las órdenes de instalación usan ya la ruta real del repositorio.

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

[unreleased]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.0...v1.0.1
[1.0.0]: https://github.com/santimartinezcordoba-prog/cli-limpiador/releases/tag/v1.0
