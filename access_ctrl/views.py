from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import ValidationError, PermissionDenied
from core.permissions import OperacionAcceso, es_admin_general, Administrador, EnrolamientoPermission, instalaciones_visibles
from .identity import normalizar, coincidencias, instalacion_consulta, bloqueos_otros, datos_personales, prohibiciones_activas, validar_documento_consulta
from django.db.models import Q, Max, Count
from django.db.models.functions import TruncDay
from django.utils import timezone
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.generics import ListAPIView, UpdateAPIView
from rest_framework.permissions import IsAuthenticated
from datetime import timedelta, datetime, time
from .models import Visita, Acceso, ProhibicionAcceso, Acceso
from core.models import Instalacion, Sector, Empresa
from core.serializers import SectorSer
from .serializers import AccesoSerializer, VisitaInlineUpdateSerializer
from .serializers import IngresoRequest, SalidaRequest, AccesoSerializer, VisitaSerializer, VisitaSimpleSerializer, \
    AccesoFullSerializer, EnrolamientoSerializer, CargaMasivaEnrolamientoSerializer
from drf_spectacular.utils import extend_schema
from openpyxl import load_workbook
from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.styles import Font, PatternFill, Alignment

def _normalizar_documento(doc: str) -> str:
    return (doc or "").replace(".", "").replace("-", "").strip().upper()

def puede_gestionar_enrolado(user, visita):
    if es_admin_general(user):
        return True

    if user.solo_enrolamiento:
        return visita.sector_id == user.sector_id

    if getattr(user, "role", None) == "admin":
        return (
            visita.instalacion is not None
            and visita.instalacion.empresa_id == user.empresa_id
        )

    return False

class AccesoListView(ListAPIView):
    serializer_class = AccesoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Acceso.objects.select_related(
            "visita",
            "instalacion",
            "sector",
            "empresa",
            "guardia",
        ).all()

        visita_id = self.request.query_params.get("visita_id")
        instalacion_id = self.request.query_params.get("instalacion_id")
        empresa_id = self.request.query_params.get("empresa_id")
        tipo = self.request.query_params.get("tipo")

        if es_admin_general(user):
            if empresa_id:
                queryset = queryset.filter(empresa_id=empresa_id)
            if instalacion_id:
                queryset = queryset.filter(instalacion_id=instalacion_id)

        elif user.role == "admin":
            queryset = queryset.filter(empresa_id=user.empresa_id)
            if instalacion_id:
                queryset = queryset.filter(instalacion_id=instalacion_id)

        elif user.role == "guardia":
            queryset = queryset.filter(
                empresa_id=user.empresa_id,
                instalacion_id=user.instalacion_id
            )

        else:
            return Acceso.objects.none()

        if visita_id:
            queryset = queryset.filter(visita_id=visita_id)

        if tipo in ["ingreso", "salida"]:
            queryset = queryset.filter(tipo=tipo)

        return queryset.order_by("-fecha_hora")


def _get_visita(payload, instalacion):
    if payload.get("visita_id"):
        return Visita.objects.filter(pk=payload["visita_id"], instalacion=instalacion).first()
    extranjero = payload.get("es_extranjero", False)
    documento = payload.get("dni_extranjero") if extranjero else payload.get("rut")
    return coincidencias(documento, extranjero).filter(instalacion=instalacion).first()


def _crear_o_actualizar_visita(payload, instalacion, sector=None):
    visita = _get_visita(payload, instalacion)
    if payload.get("visita_id") and not visita:
        raise ValidationError("La visita no pertenece a esta instalación.")
    created = visita is None
    if created:
        extranjero = payload.get("es_extranjero", False)
        documento = payload.get("dni_extranjero") if extranjero else payload.get("rut")
        source = coincidencias(documento, extranjero).filter(instalacion__empresa_id=instalacion.empresa_id).order_by("-actualizado_en").first()
        values = datos_personales(source) if source else {
            "rut": payload.get("rut"), "dni_extranjero": payload.get("dni_extranjero"),
            "es_extranjero": extranjero, "nombre": payload.get("nombre") or "Sin nombre"
        }
        visita = Visita(instalacion=instalacion, sector=sector, **values)
    for f in ("nombre", "apellido", "empresa", "patente"):
        if payload.get(f) is not None and str(payload[f]).strip():
            setattr(visita, f, payload[f])
    # A failed entry must never change another installation's enrolment or status.
    if sector:
        visita.sector = sector
    visita.save()
    return visita, created


def _hay_prohibicion(v, instalacion):
    return prohibiciones_activas().filter(visita=v, instalacion=instalacion).exists()


def _ultimo_evento(v, instalacion):
    return Acceso.objects.select_related("visita__instalacion", "instalacion", "sector", "empresa").filter(visita=v, instalacion=instalacion).order_by("-fecha_hora", "-id").first()


class IngresoView(APIView):
    permission_classes = [OperacionAcceso]

    @transaction.atomic
    @extend_schema(request=IngresoRequest, responses={201: AccesoSerializer})
    def post(self, request):
        ser = IngresoRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # ✅ 1️⃣ Obtener instalación desde el usuario logueado
        user = request.user
        if not user.instalacion:
            return Response(
                {"ok": False, "error": "usuario_sin_instalacion_asociada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        instalacion = Instalacion.objects.select_for_update().get(pk=user.instalacion_id) if user.instalacion_id else None

        # ✅ 2️⃣ Obtener el sector por ID
        sector_id = data.get("sector_id")
        if not sector_id:
            return Response(
                {"ok": False, "error": "sector_id_requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            sector = Sector.objects.get(id=sector_id, instalacion=instalacion)
        except Sector.DoesNotExist:
            return Response(
                {"ok": False, "error": "sector_no_valido"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Serialize writes in this installation and validate before updating personal data.
        visita = _get_visita(data, instalacion)
        if visita and _hay_prohibicion(visita, instalacion):
            return Response({"ok": False, "error": "prohibido"}, status=403)
        last = _ultimo_evento(visita, instalacion) if visita else None
        if last and last.tipo == "ingreso":
            return Response({"ok": False, "error": "visita_ya_adentro"}, status=409)
        visita, created = _crear_o_actualizar_visita(data, instalacion, sector)

        # ✅ 6️⃣ Registrar acceso
        acceso = Acceso.objects.create(
            visita=visita,
            instalacion=instalacion,
            sector=sector,
            tipo="ingreso",
            fecha_hora=timezone.now(),
            comentario=data.get("comentario") or "",
            guardia=user,
            empresa=instalacion.empresa,
        )

        return Response(
            {"ok": True, "mensaje": "Ingreso registrado", "acceso": AccesoSerializer(acceso).data},
            status=201
        )


class SalidaView(APIView):
    permission_classes = [OperacionAcceso]

    @transaction.atomic
    @extend_schema(request=SalidaRequest, responses={201: AccesoSerializer})
    def post(self, request):
        ser = SalidaRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # ✅ Aquí sí puedes acceder al usuario
        user = request.user
        instalacion = Instalacion.objects.select_for_update().get(pk=user.instalacion_id) if user.instalacion_id else None
        if not instalacion:
            return Response(
                {"ok": False, "error": "usuario_sin_instalacion_asociada"},
                status=400
            )

        sector_id = data.get("sector_id")
        if not sector_id:
            return Response(
                {"ok": False, "error": "sector_id_requerido"},
                status=400
            )

        try:
            sector = Sector.objects.get(id=sector_id, instalacion=instalacion)
        except Sector.DoesNotExist:
            return Response(
                {"ok": False, "error": "sector_no_valido"},
                status=404
            )

        # Aquí continúas con el flujo normal:
        visita = _get_visita(data, instalacion)
        if not visita:
            return Response({"ok": False, "error": "visita_no_encontrada"}, status=404)

        last = _ultimo_evento(visita, instalacion)
        if not last or last.tipo != "ingreso":
            return Response({"ok": False, "error": "no_hay_ingreso_abierto"}, status=409)

        if sector.pk != last.sector_id:
            raise ValidationError("La salida debe usar el sector del ingreso abierto.")
        if sector.requiere_guia and (not data.get("comentario", "").strip() or len(data.get("foto_url") or []) < 2):
            raise ValidationError("Este sector exige comentario y fotografías del documento y de la mercadería.")

        acceso = Acceso.objects.create(
            visita=visita,
            instalacion=instalacion,
            sector=sector,
            tipo="salida",
            fecha_hora=timezone.now(),
            comentario=data.get("comentario") or "",
            foto_url=data.get("foto_url") or "",
            guardia=user,
            empresa=instalacion.empresa,
        )

        return Response(
            {"ok": True, "mensaje": "Salida registrada", "acceso": AccesoSerializer(acceso).data},
            status=201
        )


class BuscarPorRUTView(APIView):
    permission_classes = [IsAuthenticated]
    extranjero = False

    def get(self, request, rut=None, dni=None):
        instalacion = instalacion_consulta(request)
        documento = validar_documento_consulta(dni if self.extranjero else rut, self.extranjero)
        matches = coincidencias(documento, self.extranjero).select_related("instalacion")
        visita = matches.filter(instalacion=instalacion).first()
        source = visita or matches.filter(instalacion__empresa_id=instalacion.empresa_id).order_by("-actualizado_en").first()
        if not source:
            return Response({"ok": False, "mensaje": "No se encontró un visitante con ese documento", "visita": None}, status=404)
        if visita:
            data = VisitaSerializer(visita).data
            warnings = data["bloqueos_otras_instalaciones"]
            blocked = data["estado"] == "prohibido"
        else:
            warnings = bloqueos_otros(documento, self.extranjero, instalacion)
            blocked = False
            # Preview only: GET must not create enrolments or transfer restrictions.
            data = {**datos_personales(source), "id": None, "estado": "activo", "comentario": "", "instalacion": instalacion.id, "sector": None, "motivo_prohibicion": None}
        message = "Acceso prohibido en esta instalación" if blocked else ("Visita encontrada" if visita else "Datos encontrados en otra instalación del cliente. Se creará un registro independiente al guardar.")
        if blocked and data.get("motivo_prohibicion"):
            message += ": " + data["motivo_prohibicion"]
        return Response({"ok": not blocked, "mensaje": message, "visita": data, "datos_copiados": visita is None, "bloqueos_otras_instalaciones": warnings}, status=403 if blocked else 200)


class BuscarPorDNIView(BuscarPorRUTView):
    extranjero = True


class RegistrarVisitaView(APIView):
    """
    Crea una nueva visita o actualiza datos mínimos si ya existe.
    """
    permission_classes = [EnrolamientoPermission]

    @extend_schema(request=VisitaSerializer, responses={201: VisitaSerializer})
    def post(self, request):
        data = request.data.copy()
        data["es_extranjero"] = bool(data.get("dni_extranjero"))
        ser = IngresoRequest(data=data)
        ser.is_valid(raise_exception=True)
        instalacion = instalacion_consulta(request)
        visita, creada = _crear_o_actualizar_visita(ser.validated_data, instalacion)

        serializer = VisitaSerializer(visita)
        mensaje = "Visita creada correctamente" if creada else "Visita actualizada correctamente"

        return Response(
            {"ok": True, "mensaje": mensaje, "visita": serializer.data},
            status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def buscar_ultimo_acceso_por_rut(request, rut):
    """
    Devuelve el último registro de acceso (ingreso o salida) asociado al RUT.
    Si no hay ingreso previo abierto, informa que no se puede registrar salida.
    Incluye información del sector visitado y si requiere documentación de salida.
    """
    instalacion = instalacion_consulta(request)
    tipo = request.query_params.get("tipo_documento")
    validar_documento_consulta(rut, extranjero=tipo != "RUT")
    matches = Visita.objects.filter(instalacion=instalacion, documento_normalizado=normalizar(rut))
    if tipo in ("RUT", "DNI"):
        matches = matches.filter(es_extranjero=tipo == "DNI")
    elif matches.count() > 1:
        raise ValidationError("Indique tipo_documento: RUT o DNI.")
    visita = matches.first()
    if not visita:
        return Response({"ok": False, "mensaje": "No existe una visita registrada con ese documento en esta instalación."}, status=404)
    ultimo = _ultimo_evento(visita, instalacion)

    if not ultimo:
        return Response(
            {"ok": False, "mensaje": "No hay registros de accesos para esta visita."},
            status=status.HTTP_404_NOT_FOUND
        )

    # ⚙️ Obtener información del sector y si requiere documentación
    requiere_doc = ultimo.sector.requiere_guia if hasattr(ultimo.sector, "requiere_guia") else False
    sector_info = {
        "id": ultimo.sector.id,
        "nombre": ultimo.sector.nombre,
        "requiere_documentacion": requiere_doc
    }

    # 🚫 Si el último evento fue una salida → no permitir otra salida
    if ultimo.tipo == "salida":
        return Response(
            {
                "ok": False,
                "mensaje": "La visita no tiene un ingreso abierto.",
                "ultimo_acceso": AccesoSerializer(ultimo).data,
                "sector": sector_info
            },
            status=status.HTTP_409_CONFLICT
        )

    # ✅ Si el último evento fue un ingreso → permitir registrar salida
    return Response(
        {
            "ok": True,
            "mensaje": "Ingreso encontrado. Puede registrar salida.",
            "ultimo_acceso": AccesoSerializer(ultimo).data,
            "sector": sector_info
        },
        status=status.HTTP_200_OK
    )


class AccesosUltimas24View(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AccesoSerializer

    def get_queryset(self):
        user = self.request.user
        now = timezone.localtime()
        start = now - timedelta(hours=24)

        qs = Acceso.objects.select_related(
            "visita",
            "instalacion",
            "sector",
            "empresa",
            "guardia"
        ).filter(
            fecha_hora__gte=start
        )

        empresa_id = self.request.query_params.get("empresa_id")
        instalacion_id = self.request.query_params.get("instalacion_id")

        if es_admin_general(user):
            if empresa_id:
                qs = qs.filter(empresa_id=empresa_id)
            if instalacion_id:
                qs = qs.filter(instalacion_id=instalacion_id)

        elif user.role == "admin":
            qs = qs.filter(empresa_id=user.empresa_id)
            if instalacion_id:
                qs = qs.filter(instalacion_id=instalacion_id)

        elif user.role == "guardia":
            qs = qs.filter(
                empresa_id=user.empresa_id,
                instalacion_id=user.instalacion_id
            )

        else:
            qs = qs.none()

        return qs.order_by("-fecha_hora")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        # Reuse the evaluated rows: no extra counts or duplicate relationship loads.
        results = serializer.data
        total = len(results)
        total_ingresos = sum(row["tipo"] == "ingreso" for row in results)
        total_salidas = sum(row["tipo"] == "salida" for row in results)

        return Response({
            "ok": True,
            "total": total,
            "total_ingresos": total_ingresos,
            "total_salidas": total_salidas,
            "results": results
        })


class AccesosDiaEnCursoView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AccesoSerializer

    def get_queryset(self):
        user = self.request.user
        now = timezone.localtime()

        start = timezone.make_aware(
            datetime.combine(now.date(), time(6, 0)),
            timezone.get_current_timezone()
        )
        next_midnight = timezone.make_aware(
            datetime.combine(now.date() + timedelta(days=1), time(0, 0)),
            timezone.get_current_timezone()
        )

        qs = Acceso.objects.select_related(
            "visita", "instalacion", "sector", "empresa", "guardia"
        ).filter(
            fecha_hora__gte=start,
            fecha_hora__lt=next_midnight
        )

        empresa_id = self.request.query_params.get("empresa_id")
        instalacion_id = self.request.query_params.get("instalacion_id")

        if es_admin_general(user):
            if empresa_id:
                qs = qs.filter(empresa_id=empresa_id)
            if instalacion_id:
                qs = qs.filter(instalacion_id=instalacion_id)

        elif user.role == "admin":
            qs = qs.filter(empresa_id=user.empresa_id)
            if instalacion_id:
                qs = qs.filter(instalacion_id=instalacion_id)

        elif user.role == "guardia":
            qs = qs.filter(
                empresa_id=user.empresa_id,
                instalacion_id=user.instalacion_id
            )

        else:
            qs = qs.none()

        return qs.order_by("-fecha_hora")

class SectoresPorInstalacionView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SectorSer

    def get_queryset(self):
        user = self.request.user
        inst_id = self.kwargs.get("instalacion_id")

        qs = Sector.objects.filter(instalacion_id=inst_id, instalacion__in=instalaciones_visibles(user))

        if es_admin_general(user):
            return qs.order_by("nombre")

        return qs.filter(instalacion__empresa_id=user.empresa_id).order_by("nombre")


class VisitasPorInstalacionView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VisitaSerializer

    def get_queryset(self):
        user = self.request.user
        instalacion_id = self.kwargs.get("instalacion_id")

        qs = Visita.objects.filter(instalacion_id=instalacion_id, instalacion__in=instalaciones_visibles(user))

        if not es_admin_general(user):
            qs = qs.filter(instalacion__empresa_id=user.empresa_id)

        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(apellido__icontains=q) |
                Q(rut__icontains=q) |
                Q(dni_extranjero__icontains=q)
            )

        return qs.order_by("-creado_en")


class AccesosPorMesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        year = int(request.query_params.get("year", timezone.localtime().year))
        month = int(request.query_params.get("month", timezone.localtime().month))

        empresa_id = request.query_params.get("empresa_id")
        instalacion_id = request.query_params.get("instalacion_id")

        base = Acceso.objects.filter(
            fecha_hora__year=year,
            fecha_hora__month=month,
        )

        if es_admin_general(user):
            if empresa_id:
                base = base.filter(empresa_id=empresa_id)
            if instalacion_id:
                base = base.filter(instalacion_id=instalacion_id)
        else:
            base = base.filter(empresa_id=user.empresa_id)
            if instalacion_id:
                base = base.filter(instalacion_id=instalacion_id)

        diario = (
            base.annotate(dia=TruncDay("fecha_hora"))
            .values("dia", "tipo")
            .annotate(total=Count("id"))
            .order_by("dia", "tipo")
        )

        include_detail = request.query_params.get("detail") == "1"
        data = {
            "year": year,
            "month": month,
            "empresa_id": empresa_id if es_admin_general(user) else user.empresa_id,
            "instalacion_id": instalacion_id,
            "resumen_diario": list(diario),
        }

        if include_detail:
            data["accesos"] = AccesoSerializer(
                base.select_related("visita", "sector", "instalacion", "empresa").order_by("-fecha_hora"),
                many=True
            ).data

        return Response({"ok": True, "data": data}, status=200)


class VisitaUpdateView(UpdateAPIView):
    permission_classes = [EnrolamientoPermission]
    serializer_class = VisitaInlineUpdateSerializer
    queryset = Visita.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if es_admin_general(user):
            return qs

        if user.solo_enrolamiento:
            return qs.filter(sector_id=user.sector_id)
        return qs.filter(instalacion__empresa_id=user.empresa_id)


class AccesoUpdateAdminView(UpdateAPIView):
    permission_classes = [Administrador]
    serializer_class = AccesoFullSerializer
    queryset = Acceso.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if es_admin_general(user):
            return qs

        if user.is_admin():
            return qs.filter(empresa_id=user.empresa_id)

        return qs.none()

    def patch(self, request, *args, **kwargs):
        user = request.user

        if not user.is_admin() and not es_admin_general(user):
            return Response(
                {"ok": False, "error": "No tiene permisos para editar accesos"},
                status=status.HTTP_403_FORBIDDEN
            )

        return self.partial_update(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        user = request.user

        if not user.is_admin() and not es_admin_general(user):
            return Response(
                {"ok": False, "error": "No tiene permisos para editar accesos"},
                status=status.HTTP_403_FORBIDDEN
            )

        return self.update(request, *args, **kwargs)


class CargaMasivaAccesosView(APIView):
    permission_classes = [Administrador]

    def post(self, request):
        if not isinstance(request.data, list):
            raise ValidationError("Debe enviar una lista de accesos.")
        creados, errores = 0, []
        for index, payload in enumerate(request.data, start=1):
            try:
                with transaction.atomic():
                    ser = IngresoRequest(data=payload)
                    ser.is_valid(raise_exception=True)
                    data = ser.validated_data
                    sector = Sector.objects.filter(pk=data.get("sector_id"), instalacion__in=instalaciones_visibles(request.user)).first()
                    if not sector:
                        raise ValidationError("Seleccione un sector de su empresa.")
                    inst = Instalacion.objects.select_for_update().get(pk=sector.instalacion_id)
                    visita = _get_visita(data, inst)
                    if visita and _hay_prohibicion(visita, inst):
                        raise ValidationError("Acceso prohibido en esta instalación.")
                    ultimo = _ultimo_evento(visita, inst) if visita else None
                    if ultimo and ultimo.tipo == "ingreso":
                        raise ValidationError("La visita ya tiene un ingreso abierto.")
                    visita, _ = _crear_o_actualizar_visita(data, inst, sector)
                    Acceso.objects.create(visita=visita, instalacion=inst, sector=sector, empresa=inst.empresa,
                        guardia=request.user, tipo="ingreso", fecha_hora=timezone.now(), comentario=data.get("comentario", ""))
                    creados += 1
            except (ValidationError, IntegrityError) as exc:
                errores.append({"fila": index, "error": str(exc)})
        return Response({"ok": not errores, "total_creados": creados, "errores": errores}, status=201)


class SectoresDisponiblesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sectores = Sector.objects.filter(instalacion__in=instalaciones_visibles(request.user))
        if request.user.solo_enrolamiento:
            sectores = sectores.filter(pk=request.user.sector_id)
        if request.query_params.get("instalacion_id"):
            sectores = sectores.filter(instalacion_id=request.query_params["instalacion_id"])
        return Response(SectorSer(sectores.order_by("nombre"), many=True).data)


class EnroladosListCreateView(APIView):
    permission_classes = [EnrolamientoPermission]

    def get(self, request):
        user = request.user

        if es_admin_general(user):
            visitas = Visita.objects.all().order_by("-id")

        elif user.solo_enrolamiento:
            visitas = Visita.objects.filter(sector=user.sector).order_by("-id")

        elif user.role == "admin":
            visitas = Visita.objects.filter(
                instalacion__empresa_id=user.empresa_id
            ).order_by("-id")

        else:
            visitas = Visita.objects.none()

        inst_id = request.query_params.get("instalacion_id")
        if inst_id:
            visitas = visitas.filter(instalacion_id=inst_id)
        serializer = EnrolamientoSerializer(visitas, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = EnrolamientoSerializer(
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)
        visita = serializer.save()

        return Response(
            EnrolamientoSerializer(visita).data,
            status=201
        )


class CargaMasivaEnrolamientoView(APIView):
    permission_classes = [EnrolamientoPermission]

    def post(self, request):
        serializer = CargaMasivaEnrolamientoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        archivo = serializer.validated_data["archivo"]

        if not archivo.name.endswith(".xlsx"):
            return Response(
                {"detail": "Solo se permiten archivos .xlsx"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user.solo_enrolamiento:
            sector = user.sector
            instalacion = user.instalacion
        else:
            sector_id = serializer.validated_data.get("sector_id")
            if not sector_id:
                return Response(
                    {"detail": "Debe enviar sector_id"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                sector = Sector.objects.get(id=sector_id)
            except Sector.DoesNotExist:
                return Response(
                    {"detail": "El sector enviado no existe"},
                    status=status.HTTP_404_NOT_FOUND
                )

            instalacion = sector.instalacion
            if not instalaciones_visibles(user).filter(pk=instalacion.pk).exists():
                raise PermissionDenied("El sector no pertenece a su empresa.")

        try:
            wb = load_workbook(filename=archivo)
            ws = wb.active
        except Exception:
            return Response(
                {"detail": "No se pudo leer el archivo Excel"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Buscar encabezados dinámicamente
        header_row_idx = None
        header_map = {}

        expected_headers = {
            "tipo documento",
            "rut",
            "dni",
            "nombre",
            "apellido",
            "patente",
            "comentario",
        }

        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            normalized = []
            for cell in row:
                if cell is None:
                    normalized.append("")
                else:
                    normalized.append(str(cell).strip().lower().replace("_", " "))

            row_headers = set(x for x in normalized if x)

            if expected_headers.issubset(row_headers):
                header_row_idx = row_idx
                for col_idx, value in enumerate(normalized):
                    if value in expected_headers:
                        header_map[value] = col_idx
                break

        if not header_row_idx:
            return Response(
                {
                    "detail": "No se encontraron los encabezados requeridos.",
                    "encabezados_requeridos": [
                        "TIPO DOCUMENTO",
                        "RUT",
                        "DNI",
                        "NOMBRE",
                        "APELLIDO",
                        "PATENTE",
                        "COMENTARIO",
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        total = 0
        creados = 0
        errores = []

        for idx, row in enumerate(
                ws.iter_rows(min_row=header_row_idx + 1, values_only=True),
                start=header_row_idx + 1
        ):
            tipo_documento = str(row[header_map["tipo documento"]]).strip().upper() if row[header_map[
                "tipo documento"]] is not None else ""
            rut = str(row[header_map["rut"]]).strip() if row[header_map["rut"]] is not None else ""
            dni_extranjero = str(row[header_map["dni"]]).strip() if row[header_map["dni"]] is not None else ""
            nombre = str(row[header_map["nombre"]]).strip() if row[header_map["nombre"]] is not None else ""
            apellido = str(row[header_map["apellido"]]).strip() if row[header_map["apellido"]] is not None else ""
            patente = str(row[header_map["patente"]]).strip() if row[header_map["patente"]] is not None else ""
            comentario = str(row[header_map["comentario"]]).strip() if row[header_map["comentario"]] is not None else ""

            empresa = sector.nombre if sector else None

            # Saltar filas completamente vacías
            if not any([tipo_documento, rut, dni_extranjero, nombre, apellido, patente, comentario]):
                continue

            total += 1

            tipo_documento_normalizado = tipo_documento.replace(" ", "").upper()

            if tipo_documento_normalizado not in ["RUT", "DNI"]:
                errores.append({
                    "fila": idx,
                    "error": "TIPO DOCUMENTO inválido. Use RUT o DNI"
                })
                continue

            if not nombre:
                errores.append({"fila": idx, "error": "NOMBRE vacío"})
                continue

            if not apellido:
                errores.append({"fila": idx, "error": "APELLIDO vacío"})
                continue

            es_extranjero = tipo_documento_normalizado == "DNI"

            if es_extranjero:
                if not dni_extranjero:
                    errores.append({
                        "fila": idx,
                        "error": "DNI vacío para registro tipo DNI"
                    })
                    continue

                if Visita.objects.filter(
                        documento_normalizado=normalizar(dni_extranjero), instalacion=instalacion,
                        es_extranjero=True
                ).exists():
                    errores.append({
                        "fila": idx,
                        "error": f"DNI duplicado: {dni_extranjero}"
                    })
                    continue

                rut = None

            else:
                if not rut:
                    errores.append({
                        "fila": idx,
                        "error": "RUT vacío para registro tipo RUT"
                    })
                    continue

                if Visita.objects.filter(
                        documento_normalizado=normalizar(rut), instalacion=instalacion,
                        es_extranjero=False
                ).exists():
                    errores.append({
                        "fila": idx,
                        "error": f"RUT duplicado: {rut}"
                    })
                    continue

                dni_extranjero = None

            try:
                Visita.objects.create(
                    rut=rut,
                    dni_extranjero=dni_extranjero,
                    es_extranjero=es_extranjero,
                    nombre=nombre,
                    apellido=apellido,
                    empresa=empresa,
                    patente=patente or None,
                    comentario=comentario or None,
                    sector=sector,
                    instalacion=instalacion,
                )
                creados += 1

            except IntegrityError:
                errores.append({
                    "fila": idx,
                    "error": "Error de integridad al guardar el registro"
                })
            except Exception as e:
                errores.append({
                    "fila": idx,
                    "error": str(e)
                })

        return Response({
            "total_filas_procesadas": total,
            "creados": creados,
            "errores": len(errores),
            "detalle_errores": errores,
            "sector_id": sector.id if sector else None,
        }, status=status.HTTP_200_OK)


class EnroladoDeleteView(APIView):
    permission_classes = [EnrolamientoPermission]

    def delete(self, request, pk):
        user = request.user

        try:
            visita = Visita.objects.get(id=pk)
        except Visita.DoesNotExist:
            return Response(
                {"detail": "Persona enrolada no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )

        if not puede_gestionar_enrolado(user, visita):
            return Response(
                {"detail": "No tiene permisos para eliminar este registro"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            visita.delete()
        except ProtectedError:
            raise ValidationError("La visita tiene historial de accesos y no se puede eliminar. Puede bloquear su acceso en esta instalación.")

        return Response(
            {"detail": "Registro eliminado correctamente"},
            status=status.HTTP_200_OK
        )


class ProhibirAccesoEnroladoView(APIView):
    permission_classes = [EnrolamientoPermission]

    def post(self, request, pk):
        user = request.user

        try:
            visita = Visita.objects.get(id=pk)
        except Visita.DoesNotExist:
            return Response(
                {"detail": "Persona enrolada no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )

        if not puede_gestionar_enrolado(user, visita):
            return Response(
                {"detail": "No tiene permisos para prohibir el acceso de este registro"},
                status=status.HTTP_403_FORBIDDEN
            )

        instalacion = visita.instalacion

        if not instalacion:
            return Response(
                {"detail": "No se pudo determinar la instalación para registrar la prohibición"},
                status=status.HTTP_400_BAD_REQUEST
            )

        prohibicion_activa = ProhibicionAcceso.objects.filter(
            visita=visita,
            instalacion=instalacion,
            fecha_fin__isnull=True
        ).exists()

        if prohibicion_activa:
            return Response(
                {"detail": "La persona ya tiene una prohibición activa en esta instalación"},
                status=status.HTTP_400_BAD_REQUEST
            )

        motivo = request.data.get("motivo", "").strip() or "Prohibición registrada desde módulo de enrolamiento"

        ProhibicionAcceso.objects.create(
            visita=visita,
            instalacion=instalacion,
            motivo=motivo,
            fecha_inicio=timezone.now(),
        )

        visita.estado = "prohibido"
        visita.save(update_fields=["estado", "actualizado_en"])

        return Response(
            {"detail": "Prohibición de acceso registrada correctamente"},
            status=status.HTTP_201_CREATED
        )


class DescargarPlantillaEnrolamientoView(APIView):
    permission_classes = [EnrolamientoPermission]

    def get(self, request):
        wb = Workbook()
        ws = wb.active
        ws.title = "Plantilla Enrolamiento"

        headers = [
            "TIPO DOCUMENTO",
            "RUT",
            "DNI",
            "NOMBRE",
            "APELLIDO",
            "PATENTE",
            "COMENTARIO",
        ]

        # Encabezados
        for col_num, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="0F2A24")
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Anchos
        widths = [20, 18, 18, 24, 24, 16, 30]
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[chr(64 + i)].width = width

        # Dropdown TIPO DOCUMENTO
        dv = DataValidation(type="list", formula1='"RUT,DNI"', allow_blank=False)
        dv.prompt = "Seleccione RUT para chilenos o DNI para extranjeros"
        dv.promptTitle = "Tipo de documento"
        dv.error = "Solo puede seleccionar RUT o DNI"
        dv.errorTitle = "Valor inválido"
        ws.add_data_validation(dv)

        # Aplicar dropdown y valor por defecto
        for row in range(2, 301):
            cell_ref = f"A{row}"
            dv.add(cell_ref)
            ws[cell_ref] = "RUT"

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="plantilla_enrolamiento.xlsx"'

        wb.save(response)
        return response


class HabilitarAccesoEnroladoView(APIView):
    permission_classes = [EnrolamientoPermission]

    def post(self, request, pk):
        user = request.user

        try:
            visita = Visita.objects.get(id=pk)
        except Visita.DoesNotExist:
            return Response(
                {"detail": "Persona enrolada no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )

        if not puede_gestionar_enrolado(user, visita):
            return Response(
                {"detail": "No tiene permisos para habilitar este registro"},
                status=status.HTTP_403_FORBIDDEN
            )

        instalacion = visita.instalacion

        if not instalacion:
            return Response(
                {"detail": "No se pudo determinar la instalación"},
                status=status.HTTP_400_BAD_REQUEST
            )

        restricciones = prohibiciones_activas().filter(visita=visita, instalacion=instalacion)

        if not restricciones.exists():
            return Response(
                {"detail": "La persona no tiene una prohibición activa en esta instalación"},
                status=status.HTTP_400_BAD_REQUEST
            )

        restricciones.update(fecha_fin=timezone.now())

        if not ProhibicionAcceso.objects.filter(
            visita=visita,
            fecha_fin__isnull=True
        ).exists():
            visita.estado = "activo"
            visita.save(update_fields=["estado", "actualizado_en"])

        return Response(
            {"detail": "Acceso habilitado correctamente"},
            status=status.HTTP_200_OK
        )
