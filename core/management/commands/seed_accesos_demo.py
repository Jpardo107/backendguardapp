import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Empresa, Instalacion, Sector
from access_ctrl.models import Visita, Acceso
from accounts.models import User


class Command(BaseCommand):
    help = "Genera accesos y salidas demo distribuidos en distintos días y horarios"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cantidad",
            type=int,
            default=80,
            help="Cantidad aproximada de ingresos a generar",
        )
        parser.add_argument(
            "--instalacion_id",
            type=int,
            required=True,
            help="ID de la instalación donde se generarán los accesos",
        )
        parser.add_argument(
            "--guardia_id",
            type=int,
            required=True,
            help="ID del guardia asociado a los registros",
        )
        parser.add_argument(
            "--empresa_id",
            type=int,
            required=True,
            help="ID de la empresa asociada a los registros",
        )
        parser.add_argument(
            "--dias_atras",
            type=int,
            default=30,
            help="Rango de días hacia atrás para distribuir los accesos",
        )

    def handle(self, *args, **options):
        cantidad = options["cantidad"]
        instalacion_id = options["instalacion_id"]
        guardia_id = options["guardia_id"]
        empresa_id = options["empresa_id"]
        dias_atras = options["dias_atras"]

        try:
            instalacion = Instalacion.objects.get(id=instalacion_id)
        except Instalacion.DoesNotExist:
            self.stdout.write(self.style.ERROR("La instalación no existe"))
            return

        try:
            guardia = User.objects.get(id=guardia_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR("El guardia no existe"))
            return

        sectores = list(Sector.objects.filter(instalacion=instalacion))
        if not sectores:
            self.stdout.write(
                self.style.ERROR("No hay sectores asociados a esa instalación")
            )
            return

        visitas = list(Visita.objects.all())
        if not visitas:
            self.stdout.write(
                self.style.ERROR("No hay visitas cargadas para usar en el seed")
            )
            return

        creados = 0
        salidas_creadas = 0

        now = timezone.now()

        for _ in range(cantidad):
            visita = random.choice(visitas)
            sector = random.choice(sectores)

            # Elegimos un día aleatorio dentro del rango
            dias_random = random.randint(0, dias_atras - 1)
            base_date = now - timedelta(days=dias_random)

            # Horario de ingreso aleatorio entre 07:00 y 19:30
            ingreso_hour = random.randint(7, 19)
            ingreso_minute = random.choice([0, 5, 10, 15, 20, 30, 40, 45, 50, 55])

            fecha_ingreso = base_date.replace(
                hour=ingreso_hour,
                minute=ingreso_minute,
                second=random.randint(0, 59),
                microsecond=0,
            )

            # Evitar fechas futuras
            if fecha_ingreso > now:
                fecha_ingreso = now - timedelta(minutes=random.randint(10, 180))

            acceso_ingreso = Acceso.objects.create(
                visita=visita,
                tipo="ingreso",
                fecha_hora=fecha_ingreso,
                comentario="Ingreso demo generado por seed",
                foto_url=[],
                instalacion=instalacion,
                sector=sector,
                guardia=guardia,
                empresa_id=empresa_id,
            )
            creados += 1

            # 80% de probabilidad de que tenga salida
            generar_salida = random.random() < 0.8

            if generar_salida:
                horas_estadia = random.randint(1, 8)
                minutos_extra = random.choice([0, 10, 15, 20, 30, 40, 50])

                fecha_salida = fecha_ingreso + timedelta(
                    hours=horas_estadia,
                    minutes=minutos_extra,
                )

                if fecha_salida <= now:
                    Acceso.objects.create(
                        visita=visita,
                        tipo="salida",
                        fecha_hora=fecha_salida,
                        comentario="Salida demo generada por seed",
                        foto_url=[],
                        instalacion=instalacion,
                        sector=sector,
                        guardia=guardia,
                        empresa_id=empresa_id,
                    )
                    salidas_creadas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed completado: {creados} ingresos y {salidas_creadas} salidas creadas."
            )
        )