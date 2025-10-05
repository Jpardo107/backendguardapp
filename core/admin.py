# core/admin.py
from django.contrib import admin
from .models import Empresa, Instalacion, Sector
admin.site.register(Empresa); admin.site.register(Instalacion); admin.site.register(Sector)