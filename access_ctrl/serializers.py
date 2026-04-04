from rest_framework import serializers
from django.utils import timezone
from .models import Visita, Acceso
from core.models import Instalacion, Sector, Empresa
from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Visita
from core.models import Sector
from django.utils import timezone
from django.db import models

User = get_user_model()

class UsuarioSerializer(serializers.ModelSerializer):
    empresa = serializers.PrimaryKeyRelatedField(
        queryset=Empresa.objects.all(),
        required=False,
        allow_null=True
    )

    instalacion_id = serializers.PrimaryKeyRelatedField(
        queryset=Instalacion.objects.all(),
        source="instalacion",
        required=False,
        allow_null=True
    )

    sector_id = serializers.PrimaryKeyRelatedField(
        queryset=Sector.objects.all(),
        source="sector",
        required=False,
        allow_null=True
    )

    sector_nombre = serializers.CharField(source="sector.nombre", read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "role",
            "empresa",
            "instalacion_id",
            "sector_id",
            "is_active",
            "sector_nombre",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)

        if password:
            user.set_password(password)
            user.save()

        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance

class VisitaSerializer(serializers.ModelSerializer):
    motivo_prohibicion = serializers.SerializerMethodField()

    class Meta:
        model = Visita
        fields = "__all__"
        extra_fields = ["motivo_prohibicion"]

    def get_motivo_prohibicion(self, obj):
        now = timezone.now()

        prohibicion = obj.prohibiciones.filter(
            fecha_inicio__lte=now
        ).filter(
            models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=now)
        ).order_by("-fecha_inicio").first()

        return prohibicion.motivo if prohibicion else None

class AccesoSerializer(serializers.ModelSerializer):
    visita = VisitaSerializer(read_only=True)
    sector_nombre = serializers.CharField(source="sector.nombre", read_only=True)
    instalacion_nombre = serializers.CharField(source="instalacion.nombre", read_only=True)
    empresa_nombre = serializers.CharField(source="empresa.nombre", read_only=True)

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
    foto_url = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        allow_null=True
    )

    def validate(self, data):
        if not data.get("visita_id") and not (data.get("rut") or data.get("dni_extranjero")):
            raise serializers.ValidationError("Debe enviar visita_id o rut/dni_extranjero.")
        return data

# ---- Visitas por instalacion ----
class VisitaSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visita
        fields = ["id", "rut", "dni_extranjero", "es_extranjero", "nombre", "apellido",
                  "empresa", "patente", "estado", "instalacion_id", "creado_en"]

# ---- Edicion accesos ----
class AccesoFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = Acceso
        fields = "__all__"  # ✅ todos los campos editables

# ---- Enrolamiento manual ----
class EnrolamientoSerializer(serializers.ModelSerializer):
    sector_id = serializers.PrimaryKeyRelatedField(
        queryset=Sector.objects.all(),
        source="sector",
        required=False
    )
    tipo_documento = serializers.CharField(write_only=True)
    dni = serializers.CharField(write_only=True, required=False, allow_blank=True)
    motivo_prohibicion = serializers.SerializerMethodField()

    class Meta:
        model = Visita
        fields = [
            "id",
            "tipo_documento",
            "rut",
            "dni",
            "nombre",
            "apellido",
            "empresa",
            "patente",
            "comentario",
            "sector_id",
            "es_extranjero",
            "dni_extranjero",
            "estado",
            "motivo_prohibicion",
        ]
        read_only_fields = [
            "es_extranjero",
            "dni_extranjero",
            "estado",
            "motivo_prohibicion",
        ]

    def get_motivo_prohibicion(self, obj):
        now = timezone.now()

        prohibicion = obj.prohibiciones.filter(
            fecha_inicio__lte=now
        ).filter(
            models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=now)
        ).order_by("-fecha_inicio").first()

        return prohibicion.motivo if prohibicion else None

    def validate(self, attrs):
        tipo_documento = (attrs.get("tipo_documento") or "").strip().upper()
        rut = (attrs.get("rut") or "").strip()
        dni = (attrs.get("dni") or "").strip()

        if tipo_documento not in ["RUT", "DNI"]:
            raise serializers.ValidationError({
                "tipo_documento": "Debe ser RUT o DNI"
            })

        if tipo_documento == "RUT":
            if not rut:
                raise serializers.ValidationError({
                    "rut": "Este campo es obligatorio cuando TIPO DOCUMENTO es RUT"
                })
            attrs["es_extranjero"] = False
            attrs["dni_extranjero"] = None

        if tipo_documento == "DNI":
            if not dni:
                raise serializers.ValidationError({
                    "dni": "Este campo es obligatorio cuando TIPO DOCUMENTO es DNI"
                })
            attrs["rut"] = None
            attrs["es_extranjero"] = True
            attrs["dni_extranjero"] = dni

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user

        validated_data.pop("tipo_documento", None)
        validated_data.pop("dni", None)

        if user.solo_enrolamiento:
            validated_data["sector"] = user.sector
            validated_data["instalacion"] = user.instalacion
            validated_data["empresa"] = user.sector.nombre if user.sector else None
        else:
            sector = validated_data.get("sector")
            if not sector:
                raise serializers.ValidationError("Debe enviar sector_id")

            validated_data["instalacion"] = sector.instalacion
            validated_data["empresa"] = sector.nombre

        return super().create(validated_data)

class CargaMasivaEnrolamientoSerializer(serializers.Serializer):
    archivo = serializers.FileField()
    sector_id = serializers.IntegerField(required=False)

class VisitaInlineUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visita
        fields = ["rut", "dni_extranjero", "nombre", "apellido", "patente"]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)

        rut = attrs.get("rut", instance.rut if instance else None)
        dni = attrs.get("dni_extranjero", instance.dni_extranjero if instance else None)
        es_extranjero = instance.es_extranjero if instance else False

        if es_extranjero:
            if not dni:
                raise serializers.ValidationError({
                    "dni_extranjero": "Este campo es obligatorio para visitas con DNI."
                })
            attrs["rut"] = None
        else:
            if not rut:
                raise serializers.ValidationError({
                    "rut": "Este campo es obligatorio para visitas con RUT."
                })
            attrs["dni_extranjero"] = None

        return attrs