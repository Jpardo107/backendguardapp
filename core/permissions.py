from rest_framework.permissions import BasePermission, SAFE_METHODS


def es_admin_general(user):
    return bool(user.is_authenticated and (user.is_superuser or user.role == "superadmin" or (
        user.role == "admin" and user.empresa and user.empresa.es_administradora_general
    )))


def es_admin_empresa(user):
    return bool(user.is_authenticated and (es_admin_general(user) or (
        user.role == "admin" and user.empresa_id
    )))


class Administrador(BasePermission):
    def has_permission(self, request, view):
        return es_admin_empresa(request.user)


class CatalogoPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.method in SAFE_METHODS or es_admin_empresa(request.user)
        )


class EnrolamientoPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            es_admin_empresa(request.user) or request.user.solo_enrolamiento
        )


def instalaciones_visibles(user):
    from .models import Instalacion
    qs = Instalacion.objects.all()
    if es_admin_general(user):
        return qs
    if user.role == "admin" and user.empresa_id:
        return qs.filter(empresa_id=user.empresa_id)
    return qs.filter(pk=user.instalacion_id, empresa_id=user.empresa_id)


class OperacionAcceso(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.role == "guardia" or es_admin_empresa(request.user))
