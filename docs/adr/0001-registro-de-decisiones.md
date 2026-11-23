# ADR-0001 — Registro de decisiones (ADRs) y separación Accion/Motor

- Estado: Aceptado
- Fecha: 2026-11-02 (semana 1; recuperado aquí porque el repo no lo versionó)

## Contexto

`limpiador` define «qué hacer» en un JSON (`acciones.json`) y lo ejecuta.
Sin un registro de decisiones, cada feature re-decide arquitectura y el
contrato (exit codes, validación, seguridad) se erosiona.

## Decisión

1. Arquitectura Accion/Motor: la interfaz (Typer+Rich en `cli.py`) solo
   decora; toda la lógica vive en módulos testeables sin CLI
   (`acciones.py`, `config.py`, …).
2. Errores y exit codes centralizados (`errores.py`).
3. Cada decisión estructural se registra en `docs/adr/NNNN-*.md` con el
   formato Contexto → Decisión → Consecuencias.
4. ADR-0002 (este número, con punto, es el que citan los comentarios del
   código de IA): decisión de la semana 3 sobre IA opcional, modo sin red
   y redacción de secretos. Ver `docs/adr/0002-…`.

## Consecuencias

- El código de red/IA es inyectable y testeable offline.
- Las auditorías (esta ADR, README) son buscables en el repo.
