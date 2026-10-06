# Gestión por empresa y separación por instalación

El administrador de empresa gestiona sus instalaciones, sectores, usuarios (incluidos guardias), visitas y bloqueos. Puede actualizar los datos de contacto de su empresa, pero no concederse administración general ni trasladar instalaciones a otro cliente.

El guardia tiene consulta de accesos e historial en la web. La API rechaza las operaciones administrativas de ese rol. Los endpoints operativos de ingreso/salida continúan disponibles para Android.

## Visitas y bloqueos

Cada documento normalizado tiene un registro independiente por instalación y tipo de documento (RUT/DNI). Las búsquedas externas se limitan a la misma empresa. La consulta devuelve una vista previa de datos personales; el registro se crea al guardar o registrar el ingreso. Nunca se copian bloqueos, estado, comentarios, sector ni historial.

`bloqueos_otras_instalaciones` informa instalación y motivo de las prohibiciones vigentes en otras instalaciones del cliente. Es informativo y no deniega el ingreso local. Se muestra en enrolamiento, registros web y búsqueda Android. Las prohibiciones locales sí deniegan el ingreso.

La edición conserva la instalación del registro. La salida busca únicamente el ingreso abierto de la instalación del guardia. RUT y DNI se distinguen explícitamente en Android.

## Migración y puesta en marcha

La migración `access_ctrl/0006_visitas_por_instalacion.py` separa registros antiguos usados en varias instalaciones y reasigna sus accesos y prohibiciones a la instalación correspondiente. Consolida duplicados del mismo documento normalizado dentro de una instalación, conservando sus accesos y prohibiciones. Después agrega la restricción de unicidad por instalación/documento/tipo.

La reversión de esquema conserva los registros separados; no vuelve a unir personas entre instalaciones. Los registros sin instalación ni historial permanecen sin asignación y no se utilizan como fuente para copiar datos entre clientes.

Antes de desplegar, respaldar la base, detener temporalmente escrituras y ejecutar en el entorno de destino:

```sh
.venv/bin/python manage.py migrate
```

Después publicar el administrador y actualizar Android. La migración se verificó en una base de pruebas; no se ejecutó sobre la base real de este proyecto.

Las instalaciones/sectores con visitas o usuarios asignados deben liberarse primero. Los registros con historial de accesos no se eliminan físicamente: se informa el motivo. Los usuarios con historial pueden desactivarse y las visitas pueden bloquearse, conservando trazabilidad.

## Verificación

```sh
.venv/bin/python manage.py test --settings=config.test_settings --noinput
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
```

`config.test_settings` usa exclusivamente SQLite en memoria, sin conectar a la base configurada por `DATABASE_URL`. Las pruebas cubren aislamiento entre instalaciones y empresas, copia de datos, alertas, bloqueos locales, permisos de guardia, CRUD del administrador, importaciones, reglas de salida y migración del historial anterior.

Web: `npm run build`. Android: `./gradlew :app:compileDebugKotlin --offline` con Java compatible con Gradle 8.9.

## Corrección de migración en PostgreSQL

Se reprodujo el fallo `cannot CREATE INDEX ... because it has pending trigger events`
con PostgreSQL 14.17 y registros históricos. La migración 0006 ahora ejecuta
`SET CONSTRAINTS ALL IMMEDIATE` después de reorganizar los datos y antes de crear
el índice único. Esto valida las relaciones pendientes sin desactivar restricciones
ni perder la protección de la transacción. También permite crear el índice diferido
del nuevo campo `documento_normalizado` al cerrar el editor de esquema.

La migración conserva el mismo nombre y esquema final. En el despliegue que falló
se vuelve a ejecutar con `python manage.py migrate` después de publicar la corrección;
no es necesario marcarla con `--fake` ni eliminar datos. Los entornos que ya aplicaron
0006 no necesitan volver a ejecutarla.

Para ejecutar las pruebas en una instancia PostgreSQL de pruebas, independiente de
`DATABASE_URL`:

```sh
INOUT_TEST_PG_HOST=127.0.0.1 INOUT_TEST_PG_PORT=5432 INOUT_TEST_PG_USER=usuario_pruebas \
  .venv/bin/python manage.py test --settings=config.settings_postgres_test --noinput
```

La conexión debe apuntar a una instancia de pruebas: el runner crea y elimina
`test_inout_migration`. La contraseña opcional se proporciona mediante
`INOUT_TEST_PG_PASSWORD`. La prueba de migración comprueba el historial, los bloqueos,
la creación efectiva del índice único y el rechazo de documentos duplicados.

Referencia: [comprobaciones diferidas de PostgreSQL](https://www.postgresql.org/docs/current/sql-set-constraints.html).
