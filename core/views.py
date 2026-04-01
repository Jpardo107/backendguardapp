from rest_framework import viewsets, permissions
from .models import Empresa, Instalacion, Sector
from .serializers import EmpresaSer, InstalacionSer, SectorSer
from rest_framework.exceptions import PermissionDenied


class BasePerm(permissions.IsAuthenticated): pass

def es_admin_general(user):
    return bool(user.empresa and user.empresa.es_administradora_general)


class EmpresaView(viewsets.ModelViewSet):
    serializer_class = EmpresaSer
    permission_classes = [BasePerm]

    def get_queryset(self):
        user = self.request.user

        if es_admin_general(user):
            return Empresa.objects.all().order_by("id")

        if user.empresa_id:
            return Empresa.objects.filter(id=user.empresa_id)

        return Empresa.objects.none()

    def perform_create(self, serializer):
        if not es_admin_general(self.request.user):
            raise PermissionDenied("No tiene permisos para crear empresas.")
        serializer.save()

    def perform_update(self, serializer):
        if not es_admin_general(self.request.user):
            raise PermissionDenied("No tiene permisos para editar empresas.")
        serializer.save()

    def perform_destroy(self, instance):
        if not es_admin_general(self.request.user):
            raise PermissionDenied("No tiene permisos para eliminar empresas.")
        instance.delete()


class InstalacionView(viewsets.ModelViewSet):
    serializer_class = InstalacionSer
    permission_classes = [BasePerm]

    def get_queryset(self):
        user = self.request.user

        if es_admin_general(user):
            return Instalacion.objects.select_related("empresa").all().order_by("id")

        if user.empresa_id:
            return Instalacion.objects.select_related("empresa").filter(
                empresa_id=user.empresa_id
            ).order_by("id")

        return Instalacion.objects.none()

    def perform_create(self, serializer):
        user = self.request.user

        if es_admin_general(user):
            serializer.save()
            return

        empresa = serializer.validated_data.get("empresa")
        if not empresa or empresa.id != user.empresa_id:
            raise PermissionDenied("Solo puede crear instalaciones para su propia empresa.")

        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user

        if es_admin_general(user):
            serializer.save()
            return

        empresa = serializer.validated_data.get("empresa", serializer.instance.empresa)
        if not empresa or empresa.id != user.empresa_id:
            raise PermissionDenied("Solo puede editar instalaciones de su propia empresa.")

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user

        if es_admin_general(user):
            instance.delete()
            return

        if instance.empresa_id != user.empresa_id:
            raise PermissionDenied("No tiene permisos para eliminar esta instalación.")

        instance.delete()


class SectorView(viewsets.ModelViewSet):
    serializer_class = SectorSer
    permission_classes = [BasePerm]

    def get_queryset(self):
        user = self.request.user

        if es_admin_general(user):
            return Sector.objects.select_related("instalacion", "instalacion__empresa").all().order_by("id")

        if user.empresa_id:
            return Sector.objects.select_related("instalacion", "instalacion__empresa").filter(
                instalacion__empresa_id=user.empresa_id
            ).order_by("id")

        return Sector.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        instalacion = serializer.validated_data.get("instalacion")

        if es_admin_general(user):
            serializer.save()
            return

        if not instalacion or instalacion.empresa_id != user.empresa_id:
            raise PermissionDenied("Solo puede crear sectores para instalaciones de su empresa.")

        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instalacion = serializer.validated_data.get("instalacion", serializer.instance.instalacion)

        if es_admin_general(user):
            serializer.save()
            return

        if not instalacion or instalacion.empresa_id != user.empresa_id:
            raise PermissionDenied("Solo puede editar sectores de su empresa.")

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user

        if es_admin_general(user):
            instance.delete()
            return

        if instance.instalacion.empresa_id != user.empresa_id:
            raise PermissionDenied("No tiene permisos para eliminar este sector.")

        instance.delete()
