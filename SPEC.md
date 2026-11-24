# Especificación actual de limpiador
1. La CLI organiza archivos mediante acciones declaradas en un JSON externo.
2. `validar` informa de errores de configuración por acción y campo.
3. `acciones` presenta en una tabla las acciones disponibles.
4. `listar` muestra los archivos de la carpeta elegida.
5. `ejecutar` muestra un plan antes de modificar archivos.
6. `--simular` muestra el plan sin modificar los archivos de trabajo.
7. Las ejecuciones y restauraciones se limitan a `~/pruebas-tareas`.
8. La ejecución requiere confirmación interactiva o la opción explícita `--si`.
9. La papelera permite restaurar operaciones registradas sin sobrescribir archivos.
10. Las acciones de IA admiten clave externa y una alternativa sin conexión.
