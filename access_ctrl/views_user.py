from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from .serializers import UsuarioSerializer

User = get_user_model()


def es_admin_general(user):
    return bool(
        getattr(user, "empresa", None)
        and getattr(user.empresa, "es_administradora_general", False)
    )


class UsuarioViewSet(viewsets.ModelViewSet):
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        qs = User.objects.select_related("empresa", "instalacion", "sector")

        # Si no es admin general, solo puede ver usuarios de su empresa
        if not es_admin_general(user):
            if not user.empresa_id:
                return User.objects.none()
            qs = qs.filter(empresa_id=user.empresa_id)

        # Filtro opcional por empresa
        empresa_id = self.request.query_params.get("empresa_id")
        if empresa_id not in [None, ""]:
            qs = qs.filter(empresa_id=empresa_id)

        # Filtro opcional por instalación
        instalacion_id = self.request.query_params.get("instalacion_id")
        if instalacion_id not in [None, ""]:
            qs = qs.filter(instalacion_id=instalacion_id)

        # Filtro opcional por rol
        role = self.request.query_params.get("role")
        if role not in [None, ""]:
            qs = qs.filter(role=role)

        return qs.order_by("username").distinct()

    def perform_create(self, serializer):
        user = self.request.user
        role = serializer.validated_data.get("role")

        # SUPERADMIN / ADMIN GENERAL
        if es_admin_general(user):
            empresa = serializer.validated_data.get("empresa")
            sector = serializer.validated_data.get("sector")

            if role == "admin":
                if not empresa:
                    raise ValidationError(
                        {"empresa": "Este campo es obligatorio para crear admin."}
                    )

                serializer.save(
                    empresa=empresa,
                    instalacion=None,
                    sector=None
                )
                return

            if role == "cliente_sector":
                if not sector:
                    raise ValidationError({"sector_id": "Este campo es obligatorio."})

                serializer.save(
                    empresa=sector.instalacion.empresa,
                    instalacion=sector.instalacion,
                    sector=sector
                )
                return

            raise ValidationError("Rol inválido.")

        # ADMIN EMPRESA NORMAL
        if user.role != "admin":
            raise PermissionDenied("Solo los admin pueden crear usuarios.")

        if role == "admin":
            serializer.save(
                empresa=user.empresa,
                instalacion=None,
                sector=None
            )
            return

        if role == "cliente_sector":
            sector = serializer.validated_data.get("sector")

            if not sector:
                raise ValidationError({"sector_id": "Este campo es obligatorio."})

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
        role = serializer.validated_data.get("role", instance.role)

        # SUPERADMIN / ADMIN GENERAL
        if es_admin_general(user):
            if role == "admin":
                empresa = serializer.validated_data.get("empresa", instance.empresa)

                if not empresa:
                    raise ValidationError(
                        {"empresa": "Este campo es obligatorio para admin."}
                    )

                serializer.save(
                    empresa=empresa,
                    instalacion=None,
                    sector=None
                )
                return

            if role == "cliente_sector":
                sector = serializer.validated_data.get("sector", instance.sector)

                if not sector:
                    raise ValidationError({"sector_id": "Este campo es obligatorio."})

                serializer.save(
                    empresa=sector.instalacion.empresa,
                    instalacion=sector.instalacion,
                    sector=sector
                )
                return

            raise ValidationError("Rol inválido.")

        # ADMIN EMPRESA NORMAL
        if user.role != "admin":
            raise PermissionDenied("Solo los admin pueden editar usuarios.")

        if instance.empresa_id != user.empresa_id:
            raise PermissionDenied("No puede editar usuarios de otra empresa.")

        if role == "admin":
            serializer.save(
                empresa=user.empresa,
                instalacion=None,
                sector=None
            )
            return

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

        if es_admin_general(user):
            instance.delete()
            return

        if user.role != "admin":
            raise PermissionDenied("Solo admin puede eliminar usuarios.")

        if instance.empresa_id != user.empresa_id:
            raise PermissionDenied("No puede eliminar usuarios de otra empresa.")

        instance.delete()