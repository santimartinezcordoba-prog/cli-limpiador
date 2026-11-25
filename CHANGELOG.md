# Changelog

Todas las diferencias notables en este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/),
y el proyecto admite [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

## [1.3.0] - 2026-11-25

### Añadido

- Acciones `agrupar-audio`, `crear-preguntas-repaso` y `extraer-tareas-pendientes`, con pruebas de IA simulada y modo offline.
- Simulación previa obligatoria y comprobación de que la carpeta no cambia durante la confirmación.

### Cambiado

- `ejecutar` y `deshacer` quedan limitados a `~/pruebas-tareas` y sus subcarpetas por seguridad; fuera de ellas no se permiten operaciones. `listar` sigue siendo de solo lectura.
- La clasificación conserva el original y crea una copia en la categoría correspondiente.
- Identificado el autor del paquete con su usuario de GitHub.

### Corregido

- Simulaciones sin comprobantes ni carpetas nuevas en disco, selección de archivos y renombrados que no repiten sufijos.
- Protección de directorios de salida y registros de IA frente a enlaces simbólicos.

### Documentación

- README: secciones explícitas «IA», «comprobar-ia» y «MCP context7» (apagado
  por defecto, para doc de httpx), códigos de salida ampliados (3 sin key en
  `comprobar-ia`, 4 degradado), tabla de campos con `modelo`/`prompt`/
  `modo_offline` y auditoría de tests completa de la semana 3. La v1.2.0 ya
  documentaba todo esto en el CHANGELOG y la skill; el README queda
  coherente con ellas.

## [1.2.0] - 2026-11-23

Semana 3: IA opcional con modo sin red, redacción de secretos y MCP de
documentación apagado por defecto.

### Añadido

- MCP `context7` en `opencode.json` con `"enabled": false`: apagado por
  defecto, se enciende con `/mcps` solo para consultar la doc de `httpx`.
  Ayuda de desarrollo, no dependencia runtime (ADR-0002).
- Dos acciones IA en el motor (`resumir-texto` y `clasificar-ficheros`) que
  hablan con el centro vía httpx 0.28 y **degradan a heurística local** si no
  hay key o falla la conexión (aviso `[modo offline]`, exit `4`). Campos de
  config `modelo` (obligatorio en IA), `prompt` y `modo_offline`
  (`heuristica`/`estricto`).
- `limpiador comprobar-ia`: smoke test del centro (key presente/ausente sin
  imprimirla, ping con timeout, latencia) con `--json`; exit `0` ok,
  `3` sin key, `4` sin red.
- `limpiador.secretos.redact()`: enmascara `sk-…`, `Bearer …` y la key exacta
  en toda salida y en el log de auditoría `log_ia.md`; carga de `.env`
  (`LIMPIADOR_IA_KEY` y compañía) sin librerías extra.
- Job CI `secret-scan` (escanea ficheros versionados y bloquea el merge si se
  filtra una key) + smoke de `comprobar-ia` (exit 3, cero filtraciones).
- Tests offline de la semana 3 (`tests/test_ia.py`, `tests/test_secretos.py`):
  `comprobar-ia` sin key/sin red/ok, acciones IA en modo offline y estricto,
  validación de `modelo`/`modo_offline`, `redact` (sk-, Bearer, asignación,
  idempotencia), `test_no_hay_claves_en_repo`, `test_redacta_clave_en_error`
  y `test_forma_obsoleta_proxies_falla`. Todos con `tmp_path` y
  monkeypatch: nunca red real.
- Skill `docs/skills/acciones-json.md` actualizada con los tipos IA y ejemplo
  `acciones.json` de 3 acciones (2 de IA); README con secciones «IA»,
  «comprobar-ia» y «MCP context7» y auditoría de tests ampliada.
- ADR-0002: IA como acción opcional — modo sin red, redacción de secretos y
  obsolescencia httpx 0.28 detectada con el MCP.

### Cambiado

- Cliente httpx migrado a la forma correcta de 0.28 tras auditar con
  `context7`: `proxies={...}` está **eliminado** en 0.28 (deprecated en 0.26);
  se usa `base_url` + `httpx.Timeout(...)` + `follow_redirects`, y `proxy=` o
  `mounts=` si algún día hiciera falta proxy. El `verify=False` del borrador
  se sustituye por CA bundle (`LIMPIADOR_CA_BUNDLE`) o verificación por
  defecto.
- `errores.py`: nuevo código `4` (`EXIT_OFFLINE`, completado en modo
  degradado) y reutilización del `3` en `comprobar-ia` para «sin key».
- Whitelist de operaciones ampliada con `resumir-texto` y
  `clasificar-ficheros`; `.gitignore` refuerza la exclusión de `.env*`
  (excepto `.env.example`).

## [1.1.1] - 2026-11-09

### Añadido

- `pytest-cov` con umbral mínimo del 80 % (`--cov-fail-under=80` en
  `addopts` + `[tool.coverage]`): la suite falla si la cobertura baja.
- CI partida en los tres jobs del spec: `lint` (ruff + mypy), `test`
  (matriz ubuntu/macos/windows × Python 3.11/3.12 + 3.10 en ubuntu, con
  cobertura) e `install-smoke` (ubuntu + 3.12, entorno limpio:
  `uv tool install .`, `version`, `--help`, `validar` con el
  `acciones.json` de ejemplo, `doctor` y comprobación de que `--simular`
  no escribe en disco).
- Tests `test_validar_renombrar_sin_sufijo` y
  `test_validar_destino_en_operacion_incompatible`.
- README: badges de CI, cobertura (gate 80 %), Python y release; tabla de
  auditoría completada con las filas de `acciones` y de
  `ejecutar`-carpeta-inexistente; sección «Cómo contribuir» con el
  checklist de PR.

### Cambiado

- `validar` emite las incoherencias operación↔campos a nivel de objeto
  con el formato exacto de la rúbrica: `acciones[N]: 'destino' es
  obligatorio cuando operacion='mover'` (y homólogos de `sufijo` y de
  destino/sufijo en operaciones incompatibles). Se siguen listando TODOS
  los errores de golpe con el índice real del array.

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

[unreleased]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/santimartinezcordoba-prog/cli-limpiador/compare/v1.0...v1.0.1
[1.0.0]: https://github.com/santimartinezcordoba-prog/cli-limpiador/releases/tag/v1.0
