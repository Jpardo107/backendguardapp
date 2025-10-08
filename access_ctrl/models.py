from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.conf import settings

class Visita(models.Model):
    rut = models.CharField(max_length=12, blank=True, null=True, db_index=True)
    dni_extranjero = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    es_extranjero = models.BooleanField(default=False)

    nombre = models.CharField(max_length=120)
    apellido = models.CharField(max_length=120, blank=True, null=True)
    empresa = models.CharField(max_length=120, blank=True, null=True)
    patente = models.CharField(max_length=12, blank=True, null=True)

    estado = models.CharField(
        max_length=20,
        choices=[("activo","Activo"),("residente","Residente"),("prohibido","Prohibido")],
        default="activo"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        doc = self.dni_extranjero if self.es_extranjero else self.rut
        return f"{self.nombre} {self.apellido or ''} - {doc or 's/doc'}"

class ProhibicionAcceso(models.Model):
    visita = models.ForeignKey(Visita, on_delete=models.CASCADE, related_name="prohibiciones")
    instalacion = models.ForeignKey("core.Instalacion", on_delete=models.CASCADE, related_name="prohibiciones")
    motivo = models.CharField(max_length=255)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["instalacion","fecha_inicio"])]

class Acceso(models.Model):
    TIPO = (("ingreso","Ingreso"), ("salida","Salida"))

    visita = models.ForeignKey(Visita, on_delete=models.PROTECT, related_name="accesos")
    instalacion = models.ForeignKey("core.Instalacion", on_delete=models.PROTECT, related_name="accesos")
    sector = models.ForeignKey("core.Sector", on_delete=models.PROTECT, related_name="accesos")
    tipo = models.CharField(max_length=10, choices=TIPO)
    fecha_hora = models.DateTimeField(db_index=True)

    comentario = models.TextField(blank=True, null=True)   # obligatorio si retiro mercadería
    foto_url = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="Permite guardar una o más URLs de fotos (compatible con SQLite y PostgreSQL)"
    )

    guardia = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="accesos_registrados")
    empresa = models.ForeignKey("core.Empresa", on_delete=models.PROTECT, related_name="accesos")

    class Meta:
        indexes = [
            models.Index(fields=["instalacion","fecha_hora"]),
            models.Index(fields=["empresa","fecha_hora"]),
            models.Index(fields=["tipo","fecha_hora"]),
        ]
