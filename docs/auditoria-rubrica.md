# Evidencias de evaluación — limpiador

Auditoría de la rama principal a 27/11/2026. Referencia inicial:
[`4d2ca893`](https://github.com/santimartinezcordoba-prog/cli-limpiador/commit/4d2ca893b0408201baf836e5100e95353c308e61).

## Matriz de la rúbrica

| Criterio | Evidencia y comprobación |
| --- | --- |
| Acciones propias | [acciones.json](../acciones.json) declara ocho acciones: cuatro locales y cuatro de IA. [test_acciones_incluidas.py](../tests/test_acciones_incluidas.py) comprueba ejecución, combinación de mover y deduplicar, y no repetir el sufijo. |
| Configuración externa | [config.py](../src/limpiador/config.py) valida campos y coherencia con Pydantic. El esquema está en el README; [ADR-0001](adr/0001-registro-de-decisiones.md) explica la separación JSON/código. Se pueden añadir reglas usando las operaciones existentes. |
| IA y secretos | [ia.py](../src/limpiador/ia.py) y [acciones_ia.py](../src/limpiador/acciones_ia.py) separan proveedor y acciones; [test_ia.py](../tests/test_ia.py) prueba el modo sin red, sin clave y proveedor simulado. [.env.example](../.env.example) es la plantilla. |
| Robustez | [errores.py](../src/limpiador/errores.py) centraliza excepciones y códigos; [test_validar.py](../tests/test_validar.py), [test_refuerzo_seguridad.py](../tests/test_refuerzo_seguridad.py) y [test_auditoria_final.py](../tests/test_auditoria_final.py) comprueban entradas erróneas, permisos, contención y recuperación parcial. |
| Diseño | [cli.py](../src/limpiador/cli.py) presenta la interfaz, [acciones.py](../src/limpiador/acciones.py) contiene el motor y la fábrica estática, [config.py](../src/limpiador/config.py) valida, [papelera.py](../src/limpiador/papelera.py) registra y restaura. |
| Pruebas | [CI](../.github/workflows/ci.yml) ejecuta pytest, Ruff, Mypy, escaneo de secretos e instalación. Los tests usan carpetas temporales y la IA está simulada. |
| Instalación y proceso | [README](../README.md) documenta uv/pipx y ejemplos; [CHANGELOG](../CHANGELOG.md), [releases](https://github.com/santimartinezcordoba-prog/cli-limpiador/releases) y [pull requests](https://github.com/santimartinezcordoba-prog/cli-limpiador/pulls?q=is%3Apr) registran el proceso. Existe la etiqueta v1.0. |

## Resultado de referencia comprobado

[CI del commit inicial](https://github.com/santimartinezcordoba-prog/cli-limpiador/actions/runs/45837174144):
diez trabajos correctos, incluidos siete entornos de pruebas y el smoke
de instalación global. El registro de Ubuntu/Python 3.12 muestra
184 pruebas superadas y 95,58 % de cobertura. Estas cifras corresponden
al commit de referencia, no a modificaciones posteriores.

## Cómo repetir la comprobación

Desde una copia del repositorio, con uv y Git instalados:

```bash
uv sync --extra dev
uv run ruff check
uv run mypy
uv run pytest
uv run python scripts/escaner_secretos.py
uv run python scripts/auditar_historial.py
```

Para comprobar la instalación como usuario, seguir la sección de
instalación del README. La CI incluye una instalación global desde
el código del checkout, no una instalación remota independiente.

## Límites y decisiones

- La exclusión de .env se incorporó en el commit ac3b8756, junto con la
  integración de IA, no en el commit inicial. No se ha reescrito el historial
  para aparentar que estaba desde el comienzo.
- El escaneo histórico busca archivos de entorno y patrones de secretos en
  referencias Git alcanzables; no demuestra la ausencia absoluta de cualquier
  secreto imaginable. La ejecución del nuevo escaneo debe confirmarse en CI.
- La recuperación de un fallo parcial reversible depende de poder escribir
  el manifiesto; si falla esa escritura se muestran los pasos completados.
  Los borrados definitivos expresamente autorizados no se pueden recuperar.
- El resultado de la IA real depende de las credenciales y del servicio del
  centro. Los tests automáticos no llaman al servicio real.
- La rúbrica exige que el alumno conozca las aserciones; la documentación
  ayuda a revisarlas, pero no acredita ese conocimiento por sí misma.
