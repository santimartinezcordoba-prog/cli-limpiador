# AGENTS.md — limpiador

CLI Python (Typer + Rich + pydantic + httpx) que limpia/ordena ficheros de forma
declarativa desde `acciones.json`. Paquete en `src/limpiador` (layout src),
entry point `limpiador = limpiador.cli:main`. Idioma del repo: **todo en
español** (código, tests, commits, docs).

## Comandos (usar uv)

```bash
uv run pytest          # suite completa; FAILA si cobertura < 80 % (addopts en pyproject)
uv run pytest tests/test_cli.py::test_nombre -x   # test único
uv run ruff check      # lint (line-length 100, py310)
uv run mypy            # mypy --strict sobre src/ y scripts/ (no tests)
uv run limpiador ...   # ejecutar la CLI desde el repo
python scripts/escaner_secretos.py   # escáner de claves (job CI secret-scan)
```

Orden de verificación local (igual que CI): `ruff check` → `mypy` → `pytest`.

## Contratos que no se pueden romper

- **Exit codes** (centralizados en `limpiador/errores.py`, documentados en README):
  0 OK/simulación/cancelación, 1 error de ejecución o `deshacer` sin manifiesto,
  2 sin TTY y sin `--si`, 3 config inválida / IA sin key, 4 degradado offline.
  Tests y CI dependen de ellos; no los cambies a la ligera.
- **Sandbox**: `ejecutar`/`deshacer` solo operan dentro de `~/pruebas-tareas`
  (`limpiador.seguridad.raiz_permitida()`, resuelto con `resolve()`).
- **`--simular` no toca disco** (ni crea carpetas): probado con hash de árbol
  (`tree_hash` en `tests/conftest.py`) y replicado en el job install-smoke de CI.
- **Whitelist de operaciones** en pydantic (`limpiador/config.py`): añadir una
  operación exige actualizar whitelist, mensajes de `validar`, README y tests.
- **Nunca imprimir/redactar mal una API key**: toda salida pasa por
  `limpiador.secretos.redact()`. `test_no_hay_claves_en_repo` + job CI
  `secret-scan` bloquean filtraciones. `.env` está gitignorado; `.env.example`
  es la plantilla.
- httpx ≥ 0.28: usar `proxy=`/`mounts=`; `proxies=` está eliminado y el test
  `test_forma_obsoleta_proxies_falla` lo fija.

## Tests: cómo escribir aquí

- Regla de oro: ningún test toca ficheros reales; todo en `tmp_path`. Usa los
  helpers de `tests/conftest.py`: `llamar()`, `escribir_config()`,
  `instantanea()`, `tree_hash()`, `salida_normalizada()` (stripea ANSI).
- El fixture autouse `_salida_determinista` borra las variables `LIMPIADOR_*`,
  cambia el cwd y **parchea `raiz_permitida` → `tmp_path`**; si pruebas el
  sandbox real, respétalo.
- Los tests de IA usan mock/respx, NUNCA red real.
- Cobertura mínima 80 % con branch coverage; `scripts/` está excluido de
  recolección (el escáner se autodetecta como test).

## Release / PR

- Commits convencionales (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`),
  una rama `feature/*` por funcionalidad, squash-merge a `main` con CI verde.
- Release: actualizar `CHANGELOG.md` + `version` en `pyproject.toml` → tag `vX.Y.Z`
  → `gh release create`. La versión vive SOLO en `pyproject.toml`.

## OpenCode en este repo

- Agente `revision-segura` (solo lectura, deny bash/edit/web) usado por
  `scripts/revision_ia.sh` sobre una copia temporal de HEAD; nunca expongas la
  copia ni `.env`.
- Skill `acciones-json` carga `docs/skills/acciones-json.md` al tocar el esquema
  de `acciones.json`; comando `/nueva-accion`.
- MCP `context7` viene **apagado** (`enabled: false`): solo encenderlo
  puntualmente para docs de httpx (ADR-0002).
  
## Normas adicionales de seguridad

- Usar HTTPS y SSLContext para la conexión con la IA.
- Nunca desactivar la verificación SSL.
- No seguir redirecciones HTTP automáticamente.
- Solicitar mi aprobación antes de modificar archivos.
- No realizar commits sin mi autorización.
- Mantener o mejorar la cobertura actual del 95,58 %.
- No modificar pruebas únicamente para aumentar la cobertura.