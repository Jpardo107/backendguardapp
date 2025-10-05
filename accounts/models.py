from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Roles(models.TextChoices):
        GUARDIA = "guardia", "Guardia"
        ADMIN = "admin", "Administrador"
        SUPERADMIN = "superadmin", "SuperAdministrador"

    role = models.CharField(max_length=20, choices=Roles.choices, default=Roles.GUARDIA)
    # Multi-tenant: opcionales (el admin/guardia suele pertenecer a una instalación)
    empresa = models.ForeignKey("core.Empresa", on_delete=models.SET_NULL, null=True, blank=True, related_name="usuarios")
    instalacion = models.ForeignKey("core.Instalacion", on_delete=models.SET_NULL, null=True, blank=True, related_name="usuarios")

    def is_admin(self): return self.role in [self.Roles.ADMIN, self.Roles.SUPERADMIN]
