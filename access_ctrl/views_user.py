from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from core.permissions import Administrador, es_admin_general, instalaciones_visibles
from .serializers import UsuarioSerializer

User = get_user_model()


class UsuarioViewSet(viewsets.ModelViewSet):
    serializer_class = UsuarioSerializer
    permission_classes = [Administrador]

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related("empresa", "instalacion", "sector")
        if not es_admin_general(user):
            qs = qs.filter(empresa_id=user.empresa_id, is_superuser=False).exclude(role="superadmin")
        for field in ("empresa_id", "instalacion_id", "role"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs.order_by("username")

    def guardar(self, serializer):
        user = self.request.user
        instance = serializer.instance
        data = serializer.validated_data
        role = data.get("role", instance.role if instance else "guardia")
        if role not in ("admin", "guardia", "cliente_sector"):
            raise ValidationError({"role": "Seleccione administrador, guardia o cliente sector."})
        if instance and instance.pk == user.pk and (role != user.role or data.get("is_active") is False):
            raise ValidationError("No puede quitarse sus propios permisos ni desactivar su sesión.")
        empresa = data.get("empresa", instance.empresa if instance else user.empresa)
        if not es_admin_general(user) and (not empresa or empresa.pk != user.empresa_id):
            raise PermissionDenied("Solo puede gestionar usuarios de su empresa.")
        if role == "admin":
            if not empresa:
                raise ValidationError({"empresa": "Seleccione una empresa."})
            serializer.save(empresa=empresa, instalacion=None, sector=None)
            return
        sector = data.get("sector", instance.sector if instance else None)
        inst = data.get("instalacion", instance.instalacion if instance else None)
        if role == "cliente_sector":
            if not sector:
                raise ValidationError({"sector_id": "Seleccione un sector."})
            if inst and sector.instalacion_id != inst.id:
                raise ValidationError({"sector_id": "El sector no pertenece a la instalación seleccionada."})
            inst = sector.instalacion
        if not inst or not instalaciones_visibles(user).filter(pk=inst.pk).exists():
            raise ValidationError({"instalacion_id": "Seleccione una instalación de su empresa."})
        serializer.save(empresa=inst.empresa, instalacion=inst, sector=sector if role == "cliente_sector" else None)

    def perform_create(self, serializer):
        if not serializer.validated_data.get("password"):
            raise ValidationError({"password": "La contraseña es obligatoria."})
        self.guardar(serializer)

    def perform_update(self, serializer):
        self.guardar(serializer)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise ValidationError("No puede eliminar su propio usuario.")
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError("Este usuario tiene accesos registrados. Puede desactivarlo para conservar el historial.")
