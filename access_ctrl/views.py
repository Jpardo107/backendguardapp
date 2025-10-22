from django.db.models import Q, Max, Count
from django.db.models.functions import TruncDay
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from datetime import timedelta, datetime, time

from .models import Visita, Acceso, ProhibicionAcceso
from core.models import Instalacion, Sector, Empresa
from .serializers import IngresoRequest, SalidaRequest, AccesoSerializer, VisitaSerializer, VisitaSimpleSerializer, \
    AccesoFullSerializer
from core.serializers import SectorSer

from drf_spectacular.utils import extend_schema

from rest_framework.generics import ListAPIView, UpdateAPIView
from rest_framework.permissions import IsAuthenticated
from .models import Acceso
from .serializers import AccesoSerializer

class AccesoListView(ListAPIView):
    serializer_class = AccesoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Acceso.objects.all()

        visita_id = self.request.query_params.get("visita_id")
        instalacion_id = self.request.query_params.get("instalacion_id")
        empresa_id = self.request.query_params.get("empresa_id")
        tipo = self.request.query_params.get("tipo")

        if visita_id:
            queryset = queryset.filter(visita_id=visita_id)
        if instalacion_id:
            queryset = queryset.filter(instalacion_id=instalacion_id)
        if empresa_id:
            queryset = queryset.filter(empresa_id=empresa_id)
        if tipo in ["ingreso", "salida"]:
            queryset = queryset.filter(tipo=tipo)

        return queryset.order_by("-fecha_hora")  # más reciente primero

def _get_visita(payload):
    # 1) por id
    if payload.get("visita_id"):
        return Visita.objects.filter(id=payload["visita_id"]).first()

    # 2) por documento
    if payload.get("es_extranjero"):
        dni = (payload.get("dni_extranjero") or "").strip()
        if dni:
            return Visita.objects.filter(dni_extranjero=dni, es_extranjero=True).first()
    else:
        rut = (payload.get("rut") or "").strip()
        if rut:
            return Visita.objects.filter(rut=rut, es_extranjero=False).first()
    return None

def _crear_o_actualizar_visita(payload):
    v = _get_visita(payload)
    if v:
        # completar datos faltantes si vienen
        for f in ["nombre","apellido","empresa","patente"]:
            val = payload.get(f)
            if val and not getattr(v, f):
                setattr(v, f, val)
        v.save()
        return v, False
    # crear
    v = Visita.objects.create(
        rut=payload.get("rut") if not payload.get("es_extranjero") else None,
        dni_extranjero=payload.get("dni_extranjero") if payload.get("es_extranjero") else None,
        es_extranjero=payload.get("es_extranjero") or False,
        nombre=payload.get("nombre") or "Sin nombre",
        apellido=payload.get("apellido") or "",
        empresa=payload.get("empresa") or "",
        patente=payload.get("patente") or "",
    )
    return v, True

def _hay_prohibicion(v, instalacion):
    now = timezone.now()
    return ProhibicionAcceso.objects.filter(
        visita=v, instalacion=instalacion
    ).filter(Q(fecha_fin__isnull=True, fecha_inicio__lte=now) | Q(fecha_inicio__lte=now, fecha_fin__gte=now)).exists()

def _ultimo_evento(v, instalacion):
    return Acceso.objects.filter(visita=v, instalacion=instalacion).order_by("-fecha_hora").first()

class IngresoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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

        instalacion = user.instalacion

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

        # ✅ 3️⃣ Crear o actualizar visita
        visita, created = _crear_o_actualizar_visita(data)

        # ✅ 4️⃣ Verificar prohibición
        if _hay_prohibicion(visita, instalacion):
            return Response(
                {"ok": False, "error": "prohibido"},
                status=status.HTTP_403_FORBIDDEN
            )

        # ✅ 5️⃣ Evitar doble ingreso
        last = _ultimo_evento(visita, instalacion)
        if last and last.tipo == "ingreso":
            return Response(
                {"ok": False, "error": "visita_ya_adentro"},
                status=status.HTTP_409_CONFLICT
            )

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
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=SalidaRequest, responses={201: AccesoSerializer})
    def post(self, request):
        ser = SalidaRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # ✅ Aquí sí puedes acceder al usuario
        user = request.user
        instalacion = user.instalacion
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
        visita = _get_visita(data)
        if not visita:
            return Response({"ok": False, "error": "visita_no_encontrada"}, status=404)

        last = _ultimo_evento(visita, instalacion)
        if not last or last.tipo != "ingreso":
            return Response({"ok": False, "error": "no_hay_ingreso_abierto"}, status=409)

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
    def get(self, request, rut):
        try:
            visita = Visita.objects.get(rut=rut)
            prohibicion = ProhibicionAcceso.objects.filter(visita=visita).exists()
            if prohibicion:
                return Response({
                    "ok": False,
                    "mensaje": "Acceso prohibido",
                    "visita": VisitaSerializer(visita).data
                }, status=status.HTTP_403_FORBIDDEN)
            return Response({
                "ok": True,
                "mensaje": "Visita encontrada",
                "visita": VisitaSerializer(visita).data
            }, status=status.HTTP_200_OK)
        except Visita.DoesNotExist:
            return Response({
                "ok": False,
                "mensaje": "No se encontró un visitante con ese RUT"
            }, status=status.HTTP_404_NOT_FOUND)

class BuscarPorDNIView(APIView):
    def get(self, request, dni):
        try:
            visita = Visita.objects.get(dni_extranjero=dni)
            prohibicion = ProhibicionAcceso.objects.filter(visita=visita).exists()
            if prohibicion:
                return Response({
                    "ok": False,
                    "mensaje": "Acceso prohibido",
                    "visita": VisitaSerializer(visita).data
                }, status=status.HTTP_403_FORBIDDEN)
            return Response({
                "ok": True,
                "mensaje": "Visita encontrada",
                "visita": VisitaSerializer(visita).data
            }, status=status.HTTP_200_OK)
        except Visita.DoesNotExist:
            return Response({
                "ok": False,
                "mensaje": "No se encontró un visitante con ese DNI"
            }, status=status.HTTP_404_NOT_FOUND)

class RegistrarVisitaView(APIView):
    """
    Crea una nueva visita o actualiza datos mínimos si ya existe.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=VisitaSerializer, responses={201: VisitaSerializer})
    def post(self, request):
        data = request.data

        # Determinar si es extranjero o no
        es_extranjero = bool(data.get("dni_extranjero"))
        data["es_extranjero"] = es_extranjero

        # Crear o actualizar usando tu función auxiliar
        visita, creada = _crear_o_actualizar_visita(data)

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
    try:
        visita = Visita.objects.get(rut=rut)
    except Visita.DoesNotExist:
        return Response(
            {"ok": False, "mensaje": "No existe una visita registrada con ese RUT."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Buscar último acceso registrado
    ultimo = Acceso.objects.filter(visita=visita).order_by("-fecha_hora").first()

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

        qs = Acceso.objects.select_related("visita", "instalacion", "sector").filter(
            fecha_hora__gte=start
        )

        # Scope por instalación
        inst_id = self.request.query_params.get("instalacion_id")
        if user.is_admin():
            if inst_id:
                qs = qs.filter(instalacion_id=inst_id)
        else:
            qs = qs.filter(instalacion_id=user.instalacion_id)

        return qs.order_by("-fecha_hora")

class AccesosDiaEnCursoView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AccesoSerializer

    def get_queryset(self):
        user = self.request.user
        now = timezone.localtime()

        # inicio a las 06:00 del día actual
        start = timezone.make_aware(datetime.combine(now.date(), time(6, 0)), timezone.get_current_timezone())
        # fin: 00:00 del día siguiente (medianoche)
        next_midnight = timezone.make_aware(datetime.combine(now.date() + timedelta(days=1), time(0, 0)),
                                            timezone.get_current_timezone())

        qs = Acceso.objects.select_related("visita", "instalacion", "sector").filter(
            fecha_hora__gte=start,
            fecha_hora__lt=next_midnight
        )

        inst_id = self.request.query_params.get("instalacion_id")
        if user.is_admin():
            if inst_id:
                qs = qs.filter(instalacion_id=inst_id)
        else:
            qs = qs.filter(instalacion_id=user.instalacion_id)

        return qs.order_by("-fecha_hora")

class SectoresPorInstalacionView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SectorSer

    def get_queryset(self):
        user = self.request.user
        inst_id = self.kwargs.get("instalacion_id")

        if not user.is_admin():
            inst_id = user.instalacion_id  # ignora ruta si no admin

        return Sector.objects.filter(instalacion_id=inst_id).order_by("nombre")

class VisitasPorInstalacionView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VisitaSimpleSerializer

    def get_queryset(self):
        user = self.request.user
        inst_id = self.kwargs.get("instalacion_id")
        if not user.is_admin():
            inst_id = user.instalacion_id

        qs = Visita.objects.filter(instalacion_id=inst_id).order_by("-creado_en")

        # filtros opcionales: ?q=texto (nombre/rut/dni)
        q = self.request.query_params.get("q")
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(apellido__icontains=q) |
                Q(rut__icontains=q) |
                Q(dni_extranjero__icontains=q)
            )
        return qs

class AccesosPorMesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        year = int(request.query_params.get("year", timezone.localtime().year))
        month = int(request.query_params.get("month", timezone.localtime().month))

        inst_id = request.query_params.get("instalacion_id")
        if not user.is_admin():
            inst_id = user.instalacion_id

        base = Acceso.objects.filter(
            instalacion_id=inst_id,
            fecha_hora__year=year,
            fecha_hora__month=month,
        )

        # Resumen diario (ingresos/salidas por día)
        diario = (base
                  .annotate(dia=TruncDay("fecha_hora"))
                  .values("dia", "tipo")
                  .annotate(total=Count("id"))
                  .order_by("dia", "tipo"))

        # Detalle opcional
        include_detail = request.query_params.get("detail") == "1"
        data = {
            "year": year, "month": month, "instalacion_id": inst_id,
            "resumen_diario": list(diario)
        }
        if include_detail:
            data["accesos"] = AccesoSerializer(
                base.select_related("visita", "sector", "instalacion").order_by("-fecha_hora"),
                many=True
            ).data

        return Response({"ok": True, "data": data}, status=200)

class VisitasPorInstalacionView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VisitaSerializer

    def get_queryset(self):
        user = self.request.user
        instalacion_id = self.kwargs.get("instalacion_id")

        # guardias: sólo sus visitas
        if not user.is_admin():
            instalacion_id = user.instalacion_id

        return Visita.objects.filter(instalacion_id=instalacion_id).order_by("-creado_en")

class VisitaUpdateView(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VisitaSerializer
    queryset = Visita.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin():
            return qs
        return qs.filter(instalacion_id=user.instalacion_id)

class AccesoUpdateAdminView(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AccesoFullSerializer
    queryset = Acceso.objects.all()

    def patch(self, request, *args, **kwargs):
        user = request.user

        # ✅ Validar que sea admin o superadmin
        if not user.is_admin():
            return Response(
                {"ok": False, "error": "No tiene permisos para editar accesos"},
                status=status.HTTP_403_FORBIDDEN
            )

        return self.partial_update(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        user = request.user
        if not user.is_admin():
            return Response(
                {"ok": False, "error": "No tiene permisos para editar accesos"},
                status=status.HTTP_403_FORBIDDEN
            )
        return self.update(request, *args, **kwargs)

class CargaMasivaAccesosView(APIView):
    def post(self, request):
        data = request.data
        if not isinstance(data, list):
            return Response({"error": "Debe enviar una lista de accesos"}, status=400)

        creados = 0
        errores = []

        for acceso_data in data:
            try:
                rut = acceso_data.get("rut")
                nombre = acceso_data.get("nombre") or "Sin nombre"

                # --- buscar o crear visita ---
                visita, creada = Visita.objects.get_or_create(
                    rut=rut,
                    defaults={
                        "dni_extranjero": acceso_data.get("dni_extranjero", ""),
                        "es_extranjero": acceso_data.get("es_extranjero", False),
                        "nombre": nombre,
                        "apellido": acceso_data.get("apellido", ""),
                        "empresa": acceso_data.get("empresa", ""),
                        "patente": acceso_data.get("patente", ""),
                    },
                )

                # --- si la visita existe pero sin nombre, actualizarla ---
                if not visita.nombre:
                    visita.nombre = nombre
                    visita.save()

                # --- crear el acceso ---
                serializer = AccesoSerializer(data={
                    "visita": visita.id,
                    "instalacion": acceso_data.get("instalacion_id"),
                    "sector": acceso_data.get("sector_id"),
                    "tipo": "ingreso",
                    "fecha_hora": timezone.now(),
                    "comentario": acceso_data.get("comentario", ""),
                    "empresa": 1,  # empresa base de pruebas
                    "guardia": 1   # usuario base de pruebas
                })

                if serializer.is_valid():
                    serializer.save()
                    creados += 1
                else:
                    errores.append(serializer.errors)

            except Exception as e:
                errores.append(str(e))

        return Response(
            {"ok": True, "total_creados": creados, "errores": errores[:10]},
            status=status.HTTP_201_CREATED
        )
