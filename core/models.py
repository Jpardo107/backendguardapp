from django.db import models

class Empresa(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    rut = models.CharField(max_length=16, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=32, blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.nombre

class Instalacion(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="instalaciones")
    nombre = models.CharField(max_length=120)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    comuna = models.CharField(max_length=120, blank=True, null=True)
    contacto_nombre = models.CharField(max_length=120, blank=True, null=True)
    contacto_email = models.EmailField(blank=True, null=True)
    contacto_telefono = models.CharField(max_length=32, blank=True, null=True)

    class Meta:
        unique_together = ("empresa","nombre")

    def __str__(self): return f"{self.nombre} ({self.empresa.nombre})"

class Sector(models.Model):
    instalacion = models.ForeignKey(Instalacion, on_delete=models.CASCADE, related_name="sectores")
    nombre = models.CharField(max_length=80)
    # NUEVO:
    requiere_guia = models.BooleanField(default=False)  # exige comentario y foto en SALIDA

    class Meta:
        unique_together = ("instalacion","nombre")


    def __str__(self): return f"{self.nombre} - {self.instalacion.nombre}"
