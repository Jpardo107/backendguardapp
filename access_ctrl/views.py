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

        instalacion = Instalacion.objects.get(id=data["instalacion_id"])
        sector = Sector.objects.get(id=data["sector_id"])

        visita, created = _crear_o_actualizar_visita(data)

        # bloqueos
        if _hay_prohibicion(visita, instalacion):
            return Response({"ok": False, "error": "prohibido"}, status=status.HTTP_403_FORBIDDEN)

        # evitar doble ingreso sin salida
        last = _ultimo_evento(visita, instalacion)
        if last and last.tipo == "ingreso":
            return Response({"ok": False, "error": "visita_ya_adentro"}, status=status.HTTP_409_CONFLICT)

        acceso = Acceso.objects.create(
            visita=visita,
            instalacion=instalacion,
            sector=sector,
            tipo="ingreso",
            fecha_hora=timezone.now(),
            comentario=data.get("comentario") or "",
            guardia=request.user,
            empresa=instalacion.empresa,
        )

        return Response({"ok": True, "acceso": AccesoSerializer(acceso).data}, status=201)

class SalidaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=SalidaRequest, responses={201: AccesoSerializer})
    def post(self, request):
        ser = SalidaRequest(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        instalacion = Instalacion.objects.get(id=data["instalacion_id"])
        sector = Sector.objects.get(id=data["sector_id"])

        visita = _get_visita(data)
        if not visita:
            return Response({"ok": False, "error": "visita_no_encontrada"}, status=404)

        # Debe existir un ingreso previo sin salida posterior
        last = _ultimo_evento(visita, instalacion)
        if not last or last.tipo != "ingreso":
            return Response({"ok": False, "error": "no_hay_ingreso_abierto"}, status=409)

        # Si el sector exige guía/foto → obligatorios
        if sector.requiere_guia:
            if not (data.get("comentario") and data.get("foto_url")):
                return Response({"ok": False, "error": "guia_y_foto_obligatorios"}, status=400)

        acceso = Acceso.objects.create(
            visita=visita,
            instalacion=instalacion,
            sector=sector,
            tipo="salida",
            fecha_hora=timezone.now(),
            comentario=data.get("comentario") or "",
            foto_url=data.get("foto_url") or "",
            guardia=request.user,
            empresa=instalacion.empresa,
        )

        return Response({"ok": True, "acceso": AccesoSerializer(acceso).data}, status=201)

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
