---
description: Propone y valida una acción de limpiador basada en una necesidad del usuario.
agent: build
---

Usa la skill acciones-json y lee el esquema actual. Para la necesidad:

$ARGUMENTS

Propón una entrada JSON y solicita la decisión del usuario si la necesidad no
es clara. Reutiliza las operaciones existentes cuando sea posible. Valida la
configuración y explica cómo simular la nueva acción en `~/pruebas-tareas`.
