from rest_framework import serializers
from .models import Empresa, Instalacion, Sector

class EmpresaSer(serializers.ModelSerializer):
    class Meta: model = Empresa; fields = "__all__"

class InstalacionSer(serializers.ModelSerializer):
    class Meta: model = Instalacion; fields = "__all__"

class SectorSer(serializers.ModelSerializer):
    class Meta: model = Sector; fields = "__all__"
