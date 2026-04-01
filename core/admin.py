from django.contrib import admin
from .models import Empresa, Instalacion, Sector


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "rut", "email", "telefono", "es_administradora_general", "creado_en")
    list_filter = ("es_administradora_general",)
    search_fields = ("nombre", "rut", "email")


@admin.register(Instalacion)
class InstalacionAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "empresa", "comuna", "contacto_nombre")
    list_filter = ("empresa",)
    search_fields = ("nombre", "empresa__nombre", "comuna")


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "instalacion", "requiere_guia")
    list_filter = ("requiere_guia", "instalacion__empresa")
    search_fields = ("nombre", "instalacion__nombre", "instalacion__empresa__nombre")