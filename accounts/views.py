from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response({
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "email": u.email,
            "role": u.role,
            "empresa_id": u.empresa_id,
            "instalacion_id": u.instalacion_id,
            "sector_id": u.sector_id,
            "solo_enrolamiento": u.solo_enrolamiento,
            "es_administradora_general": bool(
                u.empresa and u.empresa.es_administradora_general
            ),
        })