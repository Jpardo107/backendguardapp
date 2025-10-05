from rest_framework import viewsets, permissions
from .models import Empresa, Instalacion, Sector
from .serializers import EmpresaSer, InstalacionSer, SectorSer

class BasePerm(permissions.IsAuthenticated): pass

class EmpresaView(viewsets.ModelViewSet):
    queryset = Empresa.objects.all(); serializer_class = EmpresaSer; permission_classes = [BasePerm]

class InstalacionView(viewsets.ModelViewSet):
    queryset = Instalacion.objects.all(); serializer_class = InstalacionSer; permission_classes = [BasePerm]

class SectorView(viewsets.ModelViewSet):
    queryset = Sector.objects.all(); serializer_class = SectorSer; permission_classes = [BasePerm]
