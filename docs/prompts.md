# Registro de prompts y revisión

Este documento se ha añadido después del trabajo inicial. No reconstruye ni
atribuye conversaciones anteriores que no se han conservado.

## Prompts conocidos

- «Usa el subagente revisor para revisar acciones.json sin modificar archivos.»
  El resultado señaló diferencias de mayúsculas y una repetición del sufijo al
  renombrar; ambas se corrigieron en la propuesta #32. También se documentó que
  la deduplicación actúa sobre la carpeta indicada.
- El usuario pidió dos ideas útiles: generar preguntas de repaso y extraer
  tareas pendientes de apuntes. Se añadieron las dos acciones con alternativas
  locales claramente indicadas para cuando no haya conexión.

## Observación del usuario sobre OpenCode

El usuario indica que no observó fallos en OpenCode, aunque trabaja muy lento.

## Pendiente de completar por el alumno

Anota aquí los prompts que utilizaste en OpenCode durante la sesión 3 y qué
respuestas corregiste. No incluyas conversaciones no conservadas. No incluyas claves ni datos privados.

## Consulta real de Context7 — 25 de noviembre de 2026

Registro basado en la salida de OpenCode facilitada por el alumno, no en una
consulta reconstruida. Solicitó consultar Context7 sobre SSL, timeouts y
redirecciones en httpx 0.28, comparar con `src/limpiador/ia.py` y no editar archivos.

Herramientas observadas: `context7_resolve-library-id` y cuatro llamadas a
`context7_query-docs`. Se consultaron `/websites/python-httpx` (SSL, timeouts,
redirecciones y API de Client) y `/encode/httpx` (cambios de 0.28).

Conclusiones contrastadas:

- `verify=<str>` está deprecado en 0.28. Usar
  `ssl.create_default_context(cafile=...)` y pasarlo como `verify`.
- `proxies=` fue eliminado; no se utiliza en la implementación de producción.
- `httpx.Timeout` permite distinguir el tiempo de conexión de lectura.
- Se propuso desactivar redirecciones automáticas para reducir el riesgo de
  enviar datos a un destino no previsto. El informe afirmaba que httpx siempre
  reenvía Authorization al cambiar de host; no se toma esa afirmación como
  demostrada, pues httpx aplica protección al cambiar de origen.
- No se debe utilizar `verify=False` para evitar el error del certificado.

La salida del alumno indica que no modificó archivos. En el refuerzo posterior
se aplica el contexto SSL, HTTPS obligatorio, un límite de conexión de hasta
3 segundos y redirecciones desactivadas. Context7 sigue apagado por defecto en
el repositorio. El alumno debe desactivarlo también en su sesión local al terminar.

Documentación: https://www.python-httpx.org/advanced/ssl/ ;
https://www.python-httpx.org/advanced/timeouts/ ;
https://www.python-httpx.org/compatibility/ ;
https://github.com/encode/httpx/releases/tag/0.28.0
