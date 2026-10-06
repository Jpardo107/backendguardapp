from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from core.permissions import instalaciones_visibles
from .models import Visita, ProhibicionAcceso


def normalizar(doc):
    return (doc or "").replace(".", "").replace("-", "").strip().upper()


def instalacion_consulta(request):
    inst_id = request.query_params.get("instalacion_id") or request.user.instalacion_id
    if not inst_id:
        raise ValidationError("Seleccione una instalación.")
    inst = instalaciones_visibles(request.user).filter(pk=inst_id).first()
    if not inst:
        raise ValidationError("Instalación no disponible para este usuario.")
    return inst


def coincidencias(documento, extranjero):
    return Visita.objects.filter(documento_normalizado=normalizar(documento), es_extranjero=extranjero)


def prohibiciones_activas():
    now = timezone.now()
    return ProhibicionAcceso.objects.filter(fecha_inicio__lte=now).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gt=now))


def bloqueos_otros(documento, extranjero, instalacion):
    qs = prohibiciones_activas().filter(
        visita__in=coincidencias(documento, extranjero), instalacion__empresa_id=instalacion.empresa_id
    ).exclude(instalacion=instalacion).select_related("instalacion")
    return [{"instalacion_id": p.instalacion_id, "instalacion": p.instalacion.nombre, "motivo": p.motivo} for p in qs]


def datos_personales(visita):
    return {f: getattr(visita, f) for f in ("rut", "dni_extranjero", "es_extranjero", "nombre", "apellido", "empresa", "patente")}
