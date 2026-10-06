"""Request-scoped bulk loading for visit restrictions, including nested access lists."""
from collections import defaultdict

from django.db.models import Q, QuerySet
from rest_framework import serializers

from core.models import Instalacion
from .identity import prohibiciones_activas
from .models import Acceso


def preparar_estados(visitas, context):
    cache = context.setdefault("estados_visitas", {})
    pendientes = {v.pk: v for v in visitas if v.pk not in cache}
    if not pendientes:
        return cache

    # Also handles lists assembled in Python and single write responses, not just querysets.
    instalaciones = {v.instalacion_id: v._state.fields_cache["instalacion"]
                     for v in pendientes.values() if v._state.fields_cache.get("instalacion") is not None}
    faltantes = {v.instalacion_id for v in pendientes.values() if v.instalacion_id} - instalaciones.keys()
    instalaciones.update(Instalacion.objects.in_bulk(faltantes))
    for visita in pendientes.values():
        visita._state.fields_cache["instalacion"] = instalaciones.get(visita.instalacion_id)

    visitas = list(pendientes.values())
    # Bounded IN clauses work on SQLite and PostgreSQL even for unpaginated legacy lists.
    for offset in range(0, len(visitas), 400):
        lote = visitas[offset:offset + 400]
        locales = {}
        for p in prohibiciones_activas().filter(visita_id__in=[v.pk for v in lote]).order_by("-fecha_inicio", "-pk").values("visita_id", "instalacion_id", "motivo"):
            locales.setdefault((p["visita_id"], p["instalacion_id"]), p["motivo"])

        empresas = {instalaciones[v.instalacion_id].empresa_id for v in lote if v.instalacion_id in instalaciones}
        ruts = {v.documento_normalizado for v in lote if not v.es_extranjero and v.documento_normalizado}
        dnis = {v.documento_normalizado for v in lote if v.es_extranjero and v.documento_normalizado}
        otros = defaultdict(list)
        if empresas and (ruts or dnis):
            documentos = Q(visita__es_extranjero=False, visita__documento_normalizado__in=ruts) | Q(visita__es_extranjero=True, visita__documento_normalizado__in=dnis)
            qs = prohibiciones_activas().filter(documentos, instalacion__empresa_id__in=empresas).order_by("pk").values(
                "visita__documento_normalizado", "visita__es_extranjero", "instalacion__empresa_id",
                "instalacion_id", "instalacion__nombre", "motivo",
            )
            for p in qs:
                key = (p["instalacion__empresa_id"], p["visita__documento_normalizado"], p["visita__es_extranjero"])
                otros[key].append({"instalacion_id": p["instalacion_id"], "instalacion": p["instalacion__nombre"], "motivo": p["motivo"]})

        for visita in lote:
            instalacion = instalaciones.get(visita.instalacion_id)
            local_key = (visita.pk, visita.instalacion_id)
            warnings = otros.get((instalacion.empresa_id, visita.documento_normalizado, visita.es_extranjero), []) if instalacion else []
            cache[visita.pk] = {
                "bloqueado": local_key in locales,
                "motivo": locales.get(local_key),
                "otros": [p for p in warnings if p["instalacion_id"] != visita.instalacion_id],
            }
    return cache


class EstadoVisitaMixin:
    def estado_visita(self, obj):
        return preparar_estados([obj], self.context)[obj.pk]

    def get_bloqueos_otras_instalaciones(self, obj):
        return self.estado_visita(obj)["otros"]

    def get_estado(self, obj):
        return "prohibido" if self.estado_visita(obj)["bloqueado"] else ("residente" if obj.estado == "residente" else "activo")

    def get_motivo_prohibicion(self, obj):
        return self.estado_visita(obj)["motivo"]


class EstadoVisitasListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        if hasattr(data, "all"):
            data = data.all()
        if isinstance(data, QuerySet):
            if data.model is Acceso:
                data = data.select_related("visita__instalacion", "instalacion", "empresa", "sector")
            else:
                data = data.select_related("instalacion")
        rows = list(data)
        preparar_estados([row.visita if isinstance(row, Acceso) else row for row in rows], self.context)
        return super().to_representation(rows)
