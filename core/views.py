from rest_framework import viewsets, permissions
from .models import Empresa, Instalacion, Sector
from .serializers import EmpresaSer, InstalacionSer, SectorSer
from rest_framework.exceptions import PermissionDenied


class BasePerm(permissions.IsAuthenticated): pass

def es_admin_general(user):
    return bool(user.empresa and user.empresa.es_administradora_general)


class InstalacionView(viewsets.ModelViewSet):
    serializer_class = InstalacionSer
    permission_classes = [BasePerm]

    def get_queryset(self):
        user = self.request.user

        qs = Instalacion.objects.select_related("empresa").all()

        if not es_admin_general(user):
            qs = qs.filter(empresa_id=user.empresa_id)

        empresa_id = self.request.query_params.get("empresa_id")
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        return qs.order_by("id")

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


class InstalacionView(viewsets.ModelViewSet):
    serializer_class = InstalacionSer
    permission_classes = [BasePerm]

    def get_queryset(self):
        user = self.request.user

        qs = Instalacion.objects.select_related("empresa").all()

        if not es_admin_general(user):
            qs = qs.filter(empresa_id=user.empresa_id)

        empresa_id = self.request.query_params.get("empresa_id")
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        return qs.order_by("id")

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
