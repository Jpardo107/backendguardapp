from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from .serializers import UsuarioSerializer

User = get_user_model()

def es_admin_general(user):
    return bool(user.empresa and getattr(user.empresa, "es_administradora_general", False))


class UsuarioViewSet(viewsets.ModelViewSet):
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # admin → ve usuarios de su empresa
        if user.role == "admin" and user.empresa_id:
            return User.objects.filter(empresa_id=user.empresa_id).order_by("id")

        return User.objects.none()

    def perform_create(self, serializer):
        user = self.request.user

        if user.role != "admin":
            raise PermissionDenied("Solo los admin pueden crear usuarios.")

        role = serializer.validated_data.get("role")

        # 🔹 Crear ADMIN
        if role == "admin":
            serializer.save(
                empresa=user.empresa,
                instalacion=None,
                sector=None
            )
            return

        # 🔹 Crear CLIENTE SECTOR
        if role == "cliente_sector":
            sector = serializer.validated_data.get("sector")

            if not sector:
                raise ValidationError({"sector_id": "Este campo es obligatorio."})

            # Validar que el sector pertenece a la empresa del admin
            if sector.instalacion.empresa_id != user.empresa_id:
                raise PermissionDenied("No puede asignar sectores de otra empresa.")

            serializer.save(
                empresa=user.empresa,
                instalacion=sector.instalacion,
                sector=sector
            )
            return

        raise ValidationError("Rol inválido.")

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()

        if user.role != "admin":
            raise PermissionDenied("Solo los admin pueden editar usuarios.")

        if instance.empresa_id != user.empresa_id:
            raise PermissionDenied("No puede editar usuarios de otra empresa.")

        role = serializer.validated_data.get("role", instance.role)

        # 🔹 ADMIN
        if role == "admin":
            serializer.save(
                empresa=user.empresa,
                instalacion=None,
                sector=None
            )
            return

        # 🔹 CLIENTE SECTOR
        if role == "cliente_sector":
            sector = serializer.validated_data.get("sector", instance.sector)

            if not sector:
                raise ValidationError({"sector_id": "Este campo es obligatorio."})

            if sector.instalacion.empresa_id != user.empresa_id:
                raise PermissionDenied("Sector no pertenece a su empresa.")

            serializer.save(
                empresa=user.empresa,
                instalacion=sector.instalacion,
                sector=sector
            )
            return

        raise ValidationError("Rol inválido.")

    def perform_destroy(self, instance):
        user = self.request.user

        if user.role != "admin":
            raise PermissionDenied("Solo admin puede eliminar usuarios.")

        if instance.empresa_id != user.empresa_id:
            raise PermissionDenied("No puede eliminar usuarios de otra empresa.")

        instance.delete()
