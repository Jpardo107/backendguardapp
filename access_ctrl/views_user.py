from rest_framework import viewsets, permissions
from django.contrib.auth import get_user_model
from .serializers import UsuarioSerializer

User = get_user_model()

class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('id')
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]
