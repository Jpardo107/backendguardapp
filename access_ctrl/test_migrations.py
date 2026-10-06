from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class LegacyVisitMigrationTests(TransactionTestCase):
    def test_shared_visits_split_and_history_and_restrictions_remain_local(self):
        before = [("access_ctrl", "0005_visita_instalacion_visita_sector"), ("accounts", "0004_user_sector_alter_user_role_and_more")]
        after = [("access_ctrl", "0006_visitas_por_instalacion"), ("accounts", "0004_user_sector_alter_user_role_and_more")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        Empresa = apps.get_model("core", "Empresa")
        Instalacion = apps.get_model("core", "Instalacion")
        Sector = apps.get_model("core", "Sector")
        User = apps.get_model("accounts", "User")
        Visita = apps.get_model("access_ctrl", "Visita")
        Acceso = apps.get_model("access_ctrl", "Acceso")
        Prohibicion = apps.get_model("access_ctrl", "ProhibicionAcceso")
        try:
            empresa = Empresa.objects.create(nombre="Legacy")
            a = Instalacion.objects.create(empresa=empresa, nombre="Norte")
            b = Instalacion.objects.create(empresa=empresa, nombre="Sur")
            sa = Sector.objects.create(instalacion=a, nombre="A")
            sb = Sector.objects.create(instalacion=b, nombre="B")
            guardia = User.objects.create(username="migration", role="guardia", empresa=empresa, instalacion=a)
            visita = Visita.objects.create(rut="12.345.678-5", nombre="Compartida", estado="prohibido", instalacion=b, sector=sb)
            duplicate = Visita.objects.create(rut="123456785", nombre="Duplicada", instalacion=a, sector=sa)
            ids = []
            for v, inst, sector in [(visita,a,sa),(visita,b,sb),(duplicate,a,sa)]:
                ids.append(Acceso.objects.create(visita=v, instalacion=inst, sector=sector, empresa=empresa, guardia=guardia, tipo="ingreso", fecha_hora=timezone.now()).pk)
            restriction = Prohibicion.objects.create(visita=visita, instalacion=a, motivo="Solo Norte", fecha_inicio=timezone.now())
            # estado was globally prohibited but actual restriction was only in A.
            executor = MigrationExecutor(connection); executor.migrate(after)
            apps = executor.loader.project_state(after).apps
            V = apps.get_model("access_ctrl", "Visita")
            A = apps.get_model("access_ctrl", "Acceso")
            P = apps.get_model("access_ctrl", "ProhibicionAcceso")
            self.assertEqual(A.objects.filter(pk__in=ids).count(), 3)
            self.assertEqual(V.objects.filter(documento_normalizado="123456785").count(), 2)
            va = V.objects.get(instalacion=a.pk)
            vb = V.objects.get(instalacion=b.pk)
            self.assertNotEqual(va.pk, vb.pk)
            self.assertEqual(set(A.objects.filter(instalacion=a.pk).values_list("visita_id", flat=True)), {va.pk})
            self.assertEqual(set(A.objects.filter(instalacion=b.pk).values_list("visita_id", flat=True)), {vb.pk})
            self.assertEqual(P.objects.get(pk=restriction.pk).visita_id, va.pk)
            self.assertEqual(va.estado, "prohibido")
            self.assertEqual(vb.estado, "activo")
            self.assertFalse(P.objects.filter(instalacion=b.pk).exists())
            # The data migration must finish with the real unique index in place,
            # including on PostgreSQL where the FK updates queue deferred triggers.
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, V._meta.db_table)
            self.assertTrue(constraints["visita_documento_por_instalacion"]["unique"])
            with self.assertRaises(IntegrityError), transaction.atomic():
                V.objects.create(instalacion_id=a.pk, rut="12345678-5", nombre="Duplicada",
                                 documento_normalizado="123456785", es_extranjero=False)
            self.assertEqual(MigrationExecutor(connection).migration_plan(after), [])
        finally:
            MigrationExecutor(connection).migrate(after)
