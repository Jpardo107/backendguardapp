from django.db import migrations, models
from django.utils import timezone


def separar_visitas(apps, schema_editor):
    Visita = apps.get_model("access_ctrl", "Visita")
    Acceso = apps.get_model("access_ctrl", "Acceso")
    Prohibicion = apps.get_model("access_ctrl", "ProhibicionAcceso")
    Sector = apps.get_model("core", "Sector")
    alias = schema_editor.connection.alias
    visitas, accesos, prohibiciones = (m.objects.using(alias) for m in (Visita, Acceso, Prohibicion))
    originales = list(visitas.order_by("id"))
    canonical = {}
    now = timezone.now()
    for original in originales:
        doc = original.dni_extranjero if original.es_extranjero else original.rut
        normal = (doc or "").replace(".", "").replace("-", "").strip().upper()
        had_restrictions = prohibiciones.filter(visita_id=original.pk).exists()
        destinos = set(accesos.filter(visita_id=original.id).values_list("instalacion_id", flat=True))
        destinos.update(prohibiciones.filter(visita_id=original.id).values_list("instalacion_id", flat=True))
        if original.instalacion_id:
            destinos.add(original.instalacion_id)
        if not destinos:
            visitas.filter(pk=original.pk).update(documento_normalizado=normal)
            continue
        # Preserve the original id in its current installation whenever possible.
        ordered = sorted(destinos, key=lambda i: (i != original.instalacion_id, i))
        reused = False
        for inst_id in ordered:
            key = (inst_id, original.es_extranjero, normal or f"legacy:{original.pk}")
            target_id = canonical.get(key)
            sector_id = None
            if original.sector_id and Sector.objects.using(alias).filter(pk=original.sector_id, instalacion_id=inst_id).exists():
                sector_id = original.sector_id
            else:
                sector_id = accesos.filter(visita_id=original.pk, instalacion_id=inst_id).order_by("-fecha_hora", "-pk").values_list("sector_id", flat=True).first()
            if target_id is None:
                values = {f: getattr(original, f) for f in ("rut", "dni_extranjero", "es_extranjero", "nombre", "apellido", "empresa", "patente")}
                values.update(documento_normalizado=normal, instalacion_id=inst_id, sector_id=sector_id,
                              comentario=original.comentario if inst_id == original.instalacion_id else "",
                              estado="residente" if inst_id == original.instalacion_id and original.estado == "residente" else "activo")
                if not reused:
                    visitas.filter(pk=original.pk).update(**values)
                    target_id = original.pk
                    reused = True
                else:
                    target_id = visitas.create(**values).pk
                    visitas.filter(pk=target_id).update(creado_en=original.creado_en, actualizado_en=original.actualizado_en)
                canonical[key] = target_id
            accesos.filter(visita_id=original.pk, instalacion_id=inst_id).update(visita_id=target_id)
            prohibiciones.filter(visita_id=original.pk, instalacion_id=inst_id).update(visita_id=target_id)
            # Legacy estado=prohibido without a prohibition belongs only to its original installation.
            if original.estado == "prohibido" and inst_id == original.instalacion_id and not had_restrictions:
                prohibiciones.create(visita_id=target_id, instalacion_id=inst_id, motivo="Bloqueo previo (sin motivo registrado)", fecha_inicio=original.actualizado_en)
        if not reused:
            visitas.filter(pk=original.pk).delete()
    active = prohibiciones.filter(fecha_inicio__lte=now).filter(models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gt=now))
    visitas.filter(pk__in=active.values("visita_id")).update(estado="prohibido")

    if schema_editor.connection.vendor == "postgresql":
        # Reassigning foreign keys queues deferred constraint triggers. Validate
        # them before AddConstraint and AddField's deferred CREATE INDEX run.
        # Keep the migration atomic: invalid data must roll back the whole change.
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):
    dependencies = [("access_ctrl", "0005_visita_instalacion_visita_sector")]
    operations = [
        migrations.AddField(model_name="visita", name="documento_normalizado", field=models.CharField(max_length=32, blank=True, default="", db_index=True)),
        # Rolling back the schema preserves the separated records and their history.
        migrations.RunPython(separar_visitas, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="visita", constraint=models.UniqueConstraint(fields=("instalacion", "es_extranjero", "documento_normalizado"), condition=~models.Q(documento_normalizado=""), name="visita_documento_por_instalacion")),
    ]
