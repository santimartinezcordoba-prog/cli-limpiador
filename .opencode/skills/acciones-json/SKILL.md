---
name: acciones-json
description: Consulta y valida el esquema de acciones.json de limpiador al modificar acciones o su código.
---

Lee `docs/skills/acciones-json.md` y `README.md` para el esquema vigente.
Comprueba nombres únicos, campos permitidos y rutas seguras; no añadas secretos.
Ejecuta `uv run limpiador validar` y prueba los cambios mediante `--simular`
en una carpeta de `~/pruebas-tareas`. El usuario decide qué tareas necesita.
