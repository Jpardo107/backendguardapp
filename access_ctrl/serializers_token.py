from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Agrega los campos instalacion_id y empresa_id al payload del token.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Campos extra en el payload
        token["instalacion_id"] = user.instalacion_id
        token["empresa_id"] = user.empresa_id
        token["role"] = user.role

        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        # Incluye datos adicionales en la respuesta del login
        data.update({
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "empresa_id": user.empresa_id,
            "instalacion_id": user.instalacion_id,
        })
        return data
