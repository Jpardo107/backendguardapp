from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

class MeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        u = request.user
        return Response({
            "id": u.id, "username": u.username, "email": u.email,
            "role": u.role, "empresa_id": u.empresa_id, "instalacion_id": u.instalacion_id
        })
