from datetime import timedelta
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from core.models import Empresa, Instalacion, Sector
from .models import Acceso, Visita, ProhibicionAcceso
from .serializers import AccesoSerializer, EnrolamientoSerializer, VisitaSerializer


class AccessSerializationTests(APITestCase):
    def setUp(self):
        self.company = Empresa.objects.create(nombre="Cliente")
        self.other = Empresa.objects.create(nombre="Otro cliente")
        self.a = Instalacion.objects.create(empresa=self.company, nombre="A")
        self.b = Instalacion.objects.create(empresa=self.company, nombre="B")
        self.c = Instalacion.objects.create(empresa=self.other, nombre="Privada")
        self.sector = Sector.objects.create(instalacion=self.a, nombre="Recepción")
        self.guard = User.objects.create_user(username="guard", role="guardia", empresa=self.company, instalacion=self.a)
        self.client.force_authenticate(self.guard)
        self.now = timezone.now()

    def populate(self, count):
        visits = [Visita(instalacion=self.a, sector=self.sector, rut=str(10000000 + i), documento_normalizado=str(10000000+i), nombre=f"Visita {i}") for i in range(count)]
        Visita.objects.bulk_create(visits)
        Acceso.objects.bulk_create([Acceso(visita=v, instalacion=self.a, sector=self.sector, empresa=self.company, guardia=self.guard, tipo="ingreso", fecha_hora=self.now) for v in visits])
        return visits

    def block(self,visit,inst,motivo,**kwargs):
        return ProhibicionAcceso.objects.create(visita=visit, instalacion=inst, motivo=motivo, fecha_inicio=kwargs.get("start", self.now-timedelta(hours=1)), fecha_fin=kwargs.get("end"))

    def test_24h_queries_stay_bounded_with_distinct_visitors(self):
        visits = self.populate(160)
        # Repeated events must not reload the same person's local restriction.
        Acceso.objects.create(visita=visits[0],instalacion=self.a,sector=self.sector,empresa=self.company,guardia=self.guard,tipo="salida",fecha_hora=self.now)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/accesos/ultimas-24h/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['total'],161)
        self.assertEqual(response.data['total_ingresos'],160)
        self.assertEqual(response.data['total_salidas'],1)
        self.assertLessEqual(len(queries),4, f'{len(queries)} queries for 161 access events')

    def test_all_list_serializers_load_restrictions_in_bulk(self):
        self.populate(60)
        for serializer, queryset in [(VisitaSerializer,Visita.objects.all()), (EnrolamientoSerializer,Visita.objects.all()), (AccesoSerializer,Acceso.objects.all())]:
            with self.subTest(serializer=serializer.__name__), CaptureQueriesContext(connection) as queries:
                data=serializer(queryset,many=True).data
            self.assertEqual(len(data),60)
            self.assertLessEqual(len(queries),3)

    def test_large_lists_keep_all_rows_and_warnings_across_batches(self):
        visits = self.populate(805)
        elsewhere = Visita.objects.create(instalacion=self.b, rut=visits[-1].rut)
        self.block(elsewhere, self.b, 'Advertencia del último lote')
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/accesos/ultimas-24h/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 805)
        self.assertLessEqual(len(queries), 8)
        state = next(row['visita'] for row in response.data['results'] if row['visita']['id'] == visits[-1].pk)
        self.assertEqual(state['estado'], 'activo')
        self.assertEqual(state['bloqueos_otras_instalaciones'][0]['motivo'], 'Advertencia del último lote')

    def test_bulk_state_preserves_installation_document_type_and_customer_boundaries(self):
        local = self.populate(1)[0]
        elsewhere = Visita.objects.create(instalacion=self.b, rut=local.rut, nombre='Otra instalación')
        private = Visita.objects.create(instalacion=self.c, rut=local.rut, nombre='Otro cliente')
        foreign = Visita.objects.create(instalacion=self.b, dni_extranjero=local.rut, es_extranjero=True, nombre='DNI distinto')
        self.block(elsewhere,self.b,'Advertencia B')
        self.block(private,self.c,'No divulgar')
        self.block(foreign,self.b,'No confundir DNI con RUT')
        self.block(local,self.a,'Vencido',end=self.now-timedelta(seconds=1))
        self.block(local,self.a,'Futuro',start=self.now+timedelta(days=1))
        state=VisitaSerializer(Visita.objects.filter(pk=local.pk),many=True).data[0]
        self.assertEqual(state['estado'],'activo')
        self.assertIsNone(state['motivo_prohibicion'])
        self.assertEqual(state['bloqueos_otras_instalaciones'],[{'instalacion_id':self.b.pk,'instalacion':'B','motivo':'Advertencia B'}])
        self.block(local,self.a,'Vigente')
        state=VisitaSerializer(Visita.objects.get(pk=local.pk)).data
        self.assertEqual(state['estado'],'prohibido')
        self.assertEqual(state['motivo_prohibicion'],'Vigente')
        self.assertEqual(len(state['bloqueos_otras_instalaciones']),1)
        # Both clients in one global-admin list must still get distinct warnings.
        mixed=VisitaSerializer(Visita.objects.filter(pk__in=[local.pk,private.pk]),many=True).data
        self.assertEqual(next(v for v in mixed if v['id']==private.pk)['bloqueos_otras_instalaciones'],[])

    def test_missing_installation_and_empty_motive(self):
        visit=Visita.objects.create(rut='123456785',nombre='Sin instalación',estado='residente')
        state=VisitaSerializer(visit).data
        self.assertEqual(state['estado'],'residente')
        self.assertEqual(state['bloqueos_otras_instalaciones'],[])
        visit.instalacion=self.a; visit.save()
        self.block(visit,self.a,'')
        self.assertEqual(VisitaSerializer(visit).data['estado'],'prohibido')

    def test_lookup_rejects_non_document_and_bad_installation_without_server_error(self):
        for path in ['/api/visitas/buscar-rut/https%3Aexample.invalid%3Fid%3D18/', '/api/visitas/buscar-dni/https%3Aexample.invalid/', '/api/accesos/buscar-ultimo/https%3Aexample.invalid/?tipo_documento=RUT', '/api/visitas/buscar-rut/123456785/?instalacion_id=invalid']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code,400)

    def test_last_access_keeps_404_for_missing_visit_and_open_entry_response(self):
        self.assertEqual(self.client.get('/api/accesos/buscar-ultimo/123456785/').status_code,404)
        visit=self.populate(1)[0]
        response=self.client.get(f'/api/accesos/buscar-ultimo/{visit.rut}/?tipo_documento=RUT')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.data['ok'])
        self.assertEqual(response.data['sector']['id'],self.sector.pk)
