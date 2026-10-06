from io import BytesIO
from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase
from openpyxl import Workbook
from accounts.models import User
from core.models import Empresa, Instalacion, Sector
from .models import Visita, Acceso, ProhibicionAcceso


class InstalacionIsolationTests(APITestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre="Cliente")
        self.otro = Empresa.objects.create(nombre="Otro cliente")
        self.i1 = Instalacion.objects.create(empresa=self.empresa, nombre="Bodega Norte")
        self.i2 = Instalacion.objects.create(empresa=self.empresa, nombre="Bodega Sur")
        self.i3 = Instalacion.objects.create(empresa=self.otro, nombre="Privada")
        self.s1 = Sector.objects.create(instalacion=self.i1, nombre="Recepción")
        self.s2 = Sector.objects.create(instalacion=self.i2, nombre="Patio")
        self.s3 = Sector.objects.create(instalacion=self.i3, nombre="Otro")
        self.admin = User.objects.create_user(username="admin", role="admin", empresa=self.empresa)
        self.g1 = User.objects.create_user(username="g1", role="guardia", empresa=self.empresa, instalacion=self.i1)
        self.g2 = User.objects.create_user(username="g2", role="guardia", empresa=self.empresa, instalacion=self.i2)
        self.sector_user = User.objects.create_user(username="sector", role="cliente_sector", empresa=self.empresa, instalacion=self.i1, sector=self.s1)
        self.v1 = Visita.objects.create(rut="12.345.678-5", nombre="Ana", apellido="Perez", patente="ABCD12", empresa="Transportes", instalacion=self.i1, sector=self.s1, estado="prohibido")
        self.block = ProhibicionAcceso.objects.create(visita=self.v1, instalacion=self.i1, motivo="Incumplimiento de protocolo", fecha_inicio=timezone.now()-timedelta(days=1))
        self.client.force_authenticate(self.admin)

    def ingresar(self, user, sector, documento="123456785", **extra):
        self.client.force_authenticate(user)
        return self.client.post("/api/accesos/ingreso/", {"rut": documento, "sector_id": sector.id, **extra}, format="json")

    def test_lookup_copies_only_personal_data_and_warns_without_creating(self):
        self.client.force_authenticate(self.g2)
        response = self.client.get("/api/visitas/buscar-rut/123456785/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["datos_copiados"])
        self.assertEqual(response.data["visita"]["estado"], "activo")
        self.assertIsNone(response.data["visita"]["id"])
        self.assertIsNone(response.data["visita"]["sector"])
        self.assertEqual(response.data["bloqueos_otras_instalaciones"], [{"instalacion_id": self.i1.id, "instalacion": self.i1.nombre, "motivo": self.block.motivo}])
        self.assertEqual(Visita.objects.count(), 1)
        response = self.ingresar(self.g2, self.s2)
        self.assertEqual(response.status_code, 201, response.data)
        v2 = Visita.objects.get(instalacion=self.i2)
        self.assertNotEqual(v2.pk, self.v1.pk)
        self.assertEqual(v2.nombre, "Ana")
        self.assertEqual(v2.estado, "activo")
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.instalacion_id, self.i1.id)
        self.assertEqual(self.v1.estado, "prohibido")
        self.assertEqual(v2.prohibiciones.count(), 0)

    def test_local_block_denies_entry_without_updating_data(self):
        response = self.ingresar(self.g1, self.s1, nombre="Changed")
        self.assertEqual(response.status_code, 403)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.nombre, "Ana")
        self.assertEqual(Acceso.objects.count(), 0)

    def test_other_company_is_not_used_or_disclosed(self):
        outsider = Visita.objects.create(rut="99999999", nombre="Secret", instalacion=self.i3, sector=self.s3)
        ProhibicionAcceso.objects.create(visita=outsider, instalacion=self.i3, motivo="Secret reason", fecha_inicio=timezone.now())
        self.client.force_authenticate(self.g2)
        self.assertEqual(self.client.get("/api/visitas/buscar-rut/99999999/").status_code, 404)
        response = self.ingresar(self.g2, self.s2, "99999999", nombre="Local")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Visita.objects.get(instalacion=self.i2).nombre, "Local")
        self.assertEqual(self.client.get(f"/api/visitas/buscar-rut/99999999/?instalacion_id={self.i3.id}").status_code, 400)

    def test_exit_lookup_and_exit_are_local_for_rut_and_dni(self):
        self.assertEqual(self.ingresar(self.g2, self.s2).status_code, 201)
        self.client.force_authenticate(self.g1)
        self.assertEqual(self.client.get("/api/accesos/buscar-ultimo/123456785/").status_code, 404)
        self.client.force_authenticate(self.g2)
        response = self.client.get("/api/accesos/buscar-ultimo/12.345.678-5/?tipo_documento=RUT")
        self.assertEqual(response.status_code, 200)
        v2 = Visita.objects.get(instalacion=self.i2)
        self.assertEqual(self.client.post("/api/accesos/salida/", {"visita_id": self.v1.pk, "instalacion_id": self.i2.pk, "sector_id": self.s2.pk}, format="json").status_code, 404)
        self.assertEqual(self.client.post("/api/accesos/salida/", {"visita_id": v2.pk, "instalacion_id": self.i2.pk, "sector_id": self.s2.pk}, format="json").status_code, 201)
        response = self.ingresar(self.g2, self.s2, "", es_extranjero=True, dni_extranjero="PAS-123", nombre="DNI")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get("/api/accesos/buscar-ultimo/PAS123/?tipo_documento=DNI").status_code, 200)

    def test_edit_and_unblock_are_independent(self):
        v2 = Visita.objects.create(rut=self.v1.rut, nombre="Ana", instalacion=self.i2, sector=self.s2)
        self.assertEqual(self.client.patch(f"/api/visitas/{v2.pk}/", {"nombre": "Ana Sur"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(f"/api/enrolamiento/personas/{v2.pk}/prohibir/", {"motivo": "Motivo Sur"}).status_code, 201)
        self.assertEqual(self.client.post(f"/api/enrolamiento/personas/{v2.pk}/habilitar/").status_code, 200)
        self.block.refresh_from_db(); self.v1.refresh_from_db()
        self.assertIsNone(self.block.fecha_fin)
        self.assertEqual(self.v1.nombre, "Ana")
        data = self.client.get(f"/api/enrolamiento/personas/?instalacion_id={self.i2.pk}").data
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["estado"], "activo")
        self.assertEqual(data[0]["bloqueos_otras_instalaciones"][0]["motivo"], self.block.motivo)

    def test_enrolment_scope_and_duplicate_normalization(self):
        payload = {"tipo_documento": "RUT", "rut": "12345678-5", "nombre": "Ana", "sector_id": self.s2.id}
        self.assertEqual(self.client.post("/api/enrolamiento/personas/", payload).status_code, 201)
        self.assertEqual(self.client.post("/api/enrolamiento/personas/", payload).status_code, 400)
        payload["sector_id"] = self.s3.pk
        self.assertEqual(self.client.post("/api/enrolamiento/personas/", payload).status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Visita.objects.create(instalacion=self.i2, rut="12.345.678-5", nombre="Duplicate")

    def test_guard_cannot_administer_even_if_company_is_general(self):
        for general in (False, True):
            self.empresa.es_administradora_general = general; self.empresa.save()
            self.g1.empresa = self.empresa
            self.client.force_authenticate(self.g1)
            checks = [
                ("post", "/api/instalaciones/", {"nombre": "X", "empresa": self.empresa.pk}),
                ("patch", f"/api/instalaciones/{self.i1.pk}/", {"nombre": "X"}),
                ("delete", f"/api/instalaciones/{self.i1.pk}/", {}),
                ("post", "/api/sectores/", {"nombre": "X", "instalacion": self.i1.pk}),
                ("patch", f"/api/sectores/{self.s1.pk}/", {"nombre": "X"}),
                ("delete", f"/api/sectores/{self.s1.pk}/", {}),
                ("get", "/api/usuarios/", {}),
                ("post", "/api/usuarios/", {}),
                ("patch", f"/api/visitas/{self.v1.pk}/", {"nombre": "X"}),
                ("post", "/api/enrolamiento/personas/", {}),
                ("get", "/api/enrolamiento/personas/", {}),
                ("post", "/api/enrolamiento/carga-masiva/", {}),
                ("post", "/api/accesos/carga-masiva/", []),
                ("post", f"/api/enrolamiento/personas/{self.v1.pk}/habilitar/", {}),
                ("post", f"/api/enrolamiento/personas/{self.v1.pk}/prohibir/", {}),
                ("delete", f"/api/enrolamiento/personas/{self.v1.pk}/", {}),
            ]
            for method, url, payload in checks:
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, 403, (general, method, url, response.data))
            self.assertEqual([i["id"] for i in self.client.get("/api/instalaciones/").data], [self.i1.pk])
            self.assertEqual(self.client.get("/api/accesos/").status_code, 200)

    def test_company_admin_crud_catalogs_and_guards(self):
        response = self.client.post("/api/instalaciones/", {"nombre": "Nueva", "empresa": self.empresa.pk})
        self.assertEqual(response.status_code, 201)
        iid = response.data["id"]
        self.assertEqual(self.client.patch(f"/api/instalaciones/{iid}/", {"nombre": "Editada"}).status_code, 200)
        sector = self.client.post("/api/sectores/", {"nombre": "Nuevo sector", "instalacion": iid})
        self.assertEqual(sector.status_code, 201)
        sid = sector.data["id"]
        self.assertEqual(self.client.patch(f"/api/sectores/{sid}/", {"requiere_guia": True}).status_code, 200)
        guard = self.client.post("/api/usuarios/", {"username": "nuevo", "password": "localtest", "role": "guardia", "instalacion_id": iid})
        self.assertEqual(guard.status_code, 201, guard.data)
        self.assertEqual(guard.data["empresa"], self.empresa.pk)
        uid = guard.data["id"]
        self.assertEqual(self.client.patch(f"/api/usuarios/{uid}/", {"instalacion_id": self.i2.pk}).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/usuarios/{uid}/", {"instalacion_id": self.i3.pk}).status_code, 400)
        self.assertEqual(self.client.delete(f"/api/usuarios/{uid}/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/sectores/{sid}/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/instalaciones/{iid}/").status_code, 204)
        self.assertEqual(self.client.patch(f"/api/instalaciones/{self.i3.pk}/", {"nombre": "No"}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/empresas/{self.empresa.pk}/", {"es_administradora_general": True}).status_code, 403)

    def test_sector_user_only_edits_own_sector(self):
        other_sector = Sector.objects.create(instalacion=self.i1, nombre="Privado")
        other_visit = Visita.objects.create(rut="111", nombre="Otra", instalacion=self.i1, sector=other_sector)
        self.client.force_authenticate(self.sector_user)
        self.assertEqual(self.client.patch(f"/api/visitas/{other_visit.pk}/", {"nombre": "No"}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/visitas/{self.v1.pk}/", {"nombre": "Sí"}).status_code, 200)
        self.assertEqual(self.client.post("/api/sectores/", {"nombre": "No", "instalacion": self.i1.pk}).status_code, 403)
        self.assertEqual(self.client.post("/api/accesos/ingreso/", {}).status_code, 403)

    def test_spreadsheet_accepts_same_document_in_new_installation_only(self):
        def upload(sid):
            workbook = Workbook(); sheet = workbook.active
            sheet.append(["TIPO DOCUMENTO", "RUT", "DNI", "NOMBRE", "APELLIDO", "PATENTE", "COMENTARIO"])
            sheet.append(["RUT", "12345678-5", "", "Ana", "Perez", "", ""])
            stream = BytesIO(); workbook.save(stream)
            return self.client.post("/api/enrolamiento/carga-masiva/", {"sector_id": sid, "archivo": SimpleUploadedFile("visitas.xlsx", stream.getvalue())}, format="multipart")
        self.assertEqual(upload(self.s2.pk).data["creados"], 1)
        self.assertEqual(upload(self.s2.pk).data["creados"], 0)
        self.assertEqual(upload(self.s3.pk).status_code, 403)

    def test_history_cannot_be_deleted_and_guard_history_is_scoped(self):
        self.assertEqual(self.ingresar(self.g2, self.s2).status_code, 201)
        visita = Visita.objects.get(instalacion=self.i2)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f"/api/enrolamiento/personas/{visita.pk}/").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/sectores/{self.s2.pk}/").status_code, 400)
        self.client.force_authenticate(self.g1)
        self.assertEqual(self.client.get(f"/api/accesos/?instalacion_id={self.i2.pk}").data, [])

    def test_expired_and_foreign_company_blocks_do_not_warn(self):
        self.block.fecha_fin = timezone.now()-timedelta(seconds=1); self.block.save()
        outsider = Visita.objects.create(rut=self.v1.rut, nombre="Ana", instalacion=self.i3)
        ProhibicionAcceso.objects.create(visita=outsider, instalacion=self.i3, motivo="Secret", fecha_inicio=timezone.now())
        self.client.force_authenticate(self.g2)
        self.assertEqual(self.client.get("/api/visitas/buscar-rut/123456785/").data["bloqueos_otras_instalaciones"], [])
        self.assertEqual(self.ingresar(self.g1, self.s1).status_code, 201)

    def test_cannot_move_records_between_installations_or_other_clients(self):
        self.assertEqual(self.client.patch(f"/api/sectores/{self.s1.pk}/", {"instalacion": self.i2.pk}).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/instalaciones/{self.i1.pk}/", {"empresa": self.otro.pk}).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/visitas/{self.v1.pk}/", {"sector": self.s2.pk}).status_code, 400)
        self.assertEqual(self.client.post("/api/enrolamiento/personas/", {"tipo_documento": "RUT", "rut": "76543210", "nombre": "Test", "instalacion_id": self.i1.pk, "sector_id": self.s2.pk}).status_code, 400)
        extra = Sector.objects.create(instalacion=self.i1, nombre="Otro sector")
        self.client.force_authenticate(self.sector_user)
        self.assertEqual(self.client.patch(f"/api/visitas/{self.v1.pk}/", {"sector": extra.pk}).status_code, 400)

    def test_admin_bulk_access_is_scoped_and_copies_identity(self):
        response = self.client.post("/api/accesos/carga-masiva/", [{"rut": self.v1.rut, "sector_id": self.s2.pk}, {"rut": "999", "sector_id": self.s3.pk}], format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["total_creados"], 1)
        self.assertEqual(len(response.data["errores"]), 1)
        self.assertEqual(Acceso.objects.get().instalacion_id, self.i2.pk)
        self.assertEqual(Acceso.objects.get().visita.nombre, "Ana")
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.instalacion_id, self.i1.pk)

    def test_required_exit_documents_and_open_entry_sector_are_enforced(self):
        self.s2.requiere_guia = True; self.s2.save()
        self.assertEqual(self.ingresar(self.g2, self.s2).status_code, 201)
        visita = Visita.objects.get(instalacion=self.i2)
        payload = {"visita_id": visita.pk, "sector_id": self.s2.pk, "instalacion_id": self.i2.pk}
        self.assertEqual(self.client.post("/api/accesos/salida/", payload, format="json").status_code, 400)
        payload.update(comentario="Guía 123", foto_url=["https://example.com/documento.jpg", "https://example.com/carga.jpg"])
        self.assertEqual(self.client.post("/api/accesos/salida/", payload, format="json").status_code, 201)
