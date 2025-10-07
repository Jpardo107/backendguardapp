from django.db.models import Q, Max
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import Visita, Acceso, ProhibicionAcceso
from core.models import Instalacion, Sector, Empresa
from .serializers import IngresoRequest, SalidaRequest, AccesoSerializer, VisitaSerializer

from drf_spectacular.utils import extend_schema

from rest_framework.generics import ListAPIView
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

