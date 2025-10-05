# access_ctrl/admin.py
from django.contrib import admin
from .models import Visita, ProhibicionAcceso, Acceso
admin.site.register(Visita); admin.site.register(ProhibicionAcceso); admin.site.register(Acceso)
