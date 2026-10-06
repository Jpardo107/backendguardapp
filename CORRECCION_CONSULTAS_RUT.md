# Consultas de documentos y timeout de accesos — 6 de octubre de 2026

El listado de últimas 24 horas ejecutaba consultas de prohibiciones y de instalación
por cada visita serializada. Además, calculaba dos veces la prohibición local para
los campos `estado` y `motivo_prohibicion`. Con muchos registros, este trabajo
acumulado podía agotar el tiempo del worker de Gunicorn.

Ahora los serializadores de visitas, enrolamientos y accesos cargan las restricciones
en lotes de hasta 400 visitas. La caché vive solo durante la serialización de una
respuesta. Las alertas siguen limitadas al mismo cliente, separando RUT de DNI y
excluyendo la instalación actual. Una prohibición en otra instalación no cambia el
estado local. Se conserva el listado completo y el contrato de respuesta de Android.

Las consultas rechazan contenido que no corresponde a un documento; los RUT
manuales mantienen compatibilidad con los registros existentes, sin introducir
una validación nueva del dígito verificador en el backend.

## Validación local

```sh
.venv/bin/python manage.py test --settings=config.test_settings
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.test_settings
```

23 pruebas aprobadas con SQLite aislado. La regresión verifica un máximo de cuatro
consultas para 161 accesos y ocho para 805 accesos, incluyendo filtros de usuario,
sin omitir registros. También comprueba aislamiento entre clientes, instalaciones
y tipos de documento, restricciones vencidas/futuras y errores de consulta.

## Publicación

Desplegar el backend incluyendo los nuevos archivos `serialization_state.py` y
`test_serialization_performance.py`. Esta corrección no añade migraciones ni
requiere aumentar el timeout. La optimización beneficia a la app ya instalada.

Los cambios complementarios de `ControlAcceso2` requieren una nueva compilación
Android: rechazan QR sin un RUT válido, permiten enlaces con parámetro explícito
RUN/RUT y muestran mensajes de validación de DRF (`detail`, listas y campos).

La validación de cámara debe completarse en un dispositivo: probar un RUT válido,
un enlace con RUN, un QR ajeno a identidad y la entrada manual de DNI.

Los `401` seguidos de renovación de token y reintento `200` muestran recuperación
de sesión. Un `404` puede indicar una visita o historial inexistente. El motivo
exacto del `400` del log requiere el cuerpo de respuesta; el APK corregido lo
mostrará. Un listado de sectores `200 []` se debe revisar según la asignación del
usuario y su instalación.

Cambios preparados localmente; producción pendiente de despliegue y verificación.
