from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    class Roles(models.TextChoices):
        GUARDIA = "guardia", "Guardia"
        ADMIN = "admin", "Administrador"
        SUPERADMIN = "superadmin", "SuperAdministrador"
        CLIENTE_SECTOR = "cliente_sector", "Cliente Sector"

    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.GUARDIA
    )

    empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios"
    )

    instalacion = models.ForeignKey(
        "core.Instalacion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios"
    )

    sector = models.ForeignKey(
        "core.Sector",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios"
    )

    def is_admin(self):
        return self.role in [self.Roles.ADMIN, self.Roles.SUPERADMIN]

    @property
    def solo_enrolamiento(self):
        return self.role == self.Roles.CLIENTE_SECTOR and self.sector_id is not None

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(role="guardia", instalacion__isnull=False)
                    | ~Q(role="guardia")
                    | Q(is_superuser=True)
                ),
                name="guardia_requires_instalacion"
            ),
            models.CheckConstraint(
                check=(
                    Q(role="cliente_sector", sector__isnull=False)
                    | ~Q(role="cliente_sector")
                    | Q(is_superuser=True)
                ),
                name="cliente_sector_requires_sector"
            ),
        ]