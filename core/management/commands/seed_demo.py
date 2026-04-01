from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from core.models import Empresa, Instalacion, Sector
from access_ctrl.models import Visita, Acceso


class Command(BaseCommand):
    help = "Crea datos demo para probar el sistema"

    def handle(self, *args, **options):
        User = get_user_model()

        self.stdout.write(self.style.WARNING("Creando datos demo..."))

        # 1. Empresas
        empresa_admin, _ = Empresa.objects.get_or_create(
            nombre="INOUT ADMINISTRADORA",
            defaults={
                "rut": "11.111.111-1",
                "email": "admin@inout.cl",
                "telefono": "111111111",
                "es_administradora_general": True,
            }
        )

        if not empresa_admin.es_administradora_general:
            empresa_admin.es_administradora_general = True
            empresa_admin.save()

        empresa_cliente, _ = Empresa.objects.get_or_create(
            nombre="CLIENTE DEMO SPA",
            defaults={
                "rut": "22.222.222-2",
                "email": "cliente@demo.cl",
                "telefono": "222222222",
                "es_administradora_general": False,
            }
        )

        # 2. Instalación
        instalacion, _ = Instalacion.objects.get_or_create(
            nombre="Instalación Demo",
            defaults={
                "empresa": empresa_cliente,
                "direccion": "Av. Demo 123",
                "comuna": "Santiago",
                "contacto_nombre": "Juan Cliente",
                "contacto_email": "contacto@demo.cl",
                "contacto_telefono": "999999999",
            }
        )

        if instalacion.empresa_id != empresa_cliente.id:
            instalacion.empresa = empresa_cliente
            instalacion.save()

        # 3. Sectores
        sectores = []
        for nombre_sector in ["Acceso Principal", "Bodega", "Recepción"]:
            sector, _ = Sector.objects.get_or_create(
                nombre=nombre_sector,
                instalacion=instalacion,
                defaults={"requiere_guia": False}
            )
            sectores.append(sector)

        # 4. Usuarios
        def crear_usuario(username, password, role, empresa, instalacion=None, is_staff=False, is_superuser=False):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@demo.cl",
                    "role": role,
                    "empresa": empresa,
                    "instalacion": instalacion,
                    "is_staff": is_staff,
                    "is_superuser": is_superuser,
                    "is_active": True,
                }
            )

            actualizado = False

            if user.empresa_id != (empresa.id if empresa else None):
                user.empresa = empresa
                actualizado = True

            if user.instalacion_id != (instalacion.id if instalacion else None):
                user.instalacion = instalacion
                actualizado = True

            if user.role != role:
                user.role = role
                actualizado = True

            if user.is_staff != is_staff:
                user.is_staff = is_staff
                actualizado = True

            if user.is_superuser != is_superuser:
                user.is_superuser = is_superuser
                actualizado = True

            if not user.is_active:
                user.is_active = True
                actualizado = True

            user.set_password(password)
            actualizado = True

            if actualizado:
                user.save()

            return user

        admin_general = crear_usuario(
            username="admin_general",
            password="Admin12345.",
            role="superadmin",
            empresa=empresa_admin,
            instalacion=None,
            is_staff=True,
            is_superuser=True,
        )

        admin_cliente = crear_usuario(
            username="admin_cliente",
            password="Admin12345.",
            role="admin",
            empresa=empresa_cliente,
            instalacion=instalacion,
            is_staff=True,
            is_superuser=False,
        )

        guardia = crear_usuario(
            username="guardia_demo",
            password="Guardia12345.",
            role="guardia",
            empresa=empresa_cliente,
            instalacion=instalacion,
            is_staff=False,
            is_superuser=False,
        )

        # 5. Visitas
        visitas_data = [
            {
                "rut": "10.000.000-1",
                "nombre": "Carlos",
                "apellido": "Soto",
                "empresa": "Proveedor Uno",
                "patente": "AA1111",
            },
            {
                "rut": "10.000.000-2",
                "nombre": "María",
                "apellido": "Lagos",
                "empresa": "Proveedor Dos",
                "patente": "BB2222",
            },
            {
                "rut": "10.000.000-3",
                "nombre": "Pedro",
                "apellido": "Reyes",
                "empresa": "Proveedor Tres",
                "patente": "CC3333",
            },
        ]

        visitas = []
        for item in visitas_data:
            visita, _ = Visita.objects.get_or_create(
                rut=item["rut"],
                defaults={
                    "nombre": item["nombre"],
                    "apellido": item["apellido"],
                    "empresa": item["empresa"],
                    "patente": item["patente"],
                    "es_extranjero": False,
                }
            )
            visitas.append(visita)

        # 6. Accesos demo últimas 24h
        ahora = timezone.now()

        combinaciones = [
            (visitas[0], sectores[0], "ingreso", ahora - timedelta(hours=2)),
            (visitas[0], sectores[0], "salida",  ahora - timedelta(hours=1, minutes=20)),
            (visitas[1], sectores[1], "ingreso", ahora - timedelta(hours=5)),
            (visitas[2], sectores[2], "ingreso", ahora - timedelta(hours=10)),
            (visitas[2], sectores[2], "salida",  ahora - timedelta(hours=9, minutes=15)),
        ]

        for visita, sector, tipo, fecha in combinaciones:
            existe = Acceso.objects.filter(
                visita=visita,
                sector=sector,
                tipo=tipo,
                fecha_hora=fecha,
            ).exists()

            if not existe:
                Acceso.objects.create(
                    visita=visita,
                    instalacion=instalacion,
                    sector=sector,
                    tipo=tipo,
                    fecha_hora=fecha,
                    comentario=f"{tipo} demo",
                    guardia=guardia,
                    empresa=empresa_cliente,
                )

        self.stdout.write(self.style.SUCCESS("Datos demo creados correctamente."))
        self.stdout.write(self.style.SUCCESS("Usuarios de prueba:"))
        self.stdout.write(" - admin_general / Admin12345.")
        self.stdout.write(" - admin_cliente / Admin12345.")
        self.stdout.write(" - guardia_demo / Guardia12345.")