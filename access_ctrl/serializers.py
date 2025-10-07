from rest_framework import serializers
from django.utils import timezone
from .models import Visita, Acceso
from core.models import Instalacion, Sector
from django.contrib.auth import get_user_model

User = get_user_model()

class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff']
        read_only_fields = ['id', 'is_staff']


class VisitaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visita
        fields = "__all__"

class AccesoSerializer(serializers.ModelSerializer):
    visita = VisitaSerializer(read_only=True)
    class Meta:
        model = Acceso
        fields = "__all__"

# ---- Ingreso ----
class IngresoRequest(serializers.Serializer):
    # Identificador de la persona
    visita_id = serializers.IntegerField(required=False)
    rut = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    dni_extranjero = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    es_extranjero = serializers.BooleanField(default=False)

    # Datos opcionales si hay que crear/actualizar
    nombre = serializers.CharField(required=False, allow_blank=True)
    apellido = serializers.CharField(required=False, allow_blank=True)
    empresa = serializers.CharField(required=False, allow_blank=True)
    patente = serializers.CharField(required=False, allow_blank=True)

    instalacion_id = serializers.IntegerField(required=False)
    sector_id = serializers.IntegerField()
    comentario = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if not data.get("visita_id") and not (data.get("rut") or data.get("dni_extranjero")):
            raise serializers.ValidationError("Debe enviar visita_id o rut/dni_extranjero.")
        return data

# ---- Salida ----
class SalidaRequest(serializers.Serializer):
    visita_id = serializers.IntegerField(required=False)
    rut = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    dni_extranjero = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    es_extranjero = serializers.BooleanField(default=False)

    instalacion_id = serializers.IntegerField()
    sector_id = serializers.IntegerField()
    comentario = serializers.CharField(required=False, allow_blank=True)
    foto_url = serializers.URLField(required=False, allow_blank=True)

    def validate(self, data):
        if not data.get("visita_id") and not (data.get("rut") or data.get("dni_extranjero")):
            raise serializers.ValidationError("Debe enviar visita_id o rut/dni_extranjero.")
        return data
