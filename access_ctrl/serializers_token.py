from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        es_admin_general = bool(
            user.empresa and user.empresa.es_administradora_general
        )

        token["instalacion_id"] = user.instalacion_id
        token["empresa_id"] = user.empresa_id
        token["sector_id"] = user.sector_id
        token["role"] = user.role
        token["es_administradora_general"] = es_admin_general
        token["solo_enrolamiento"] = user.solo_enrolamiento

        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        es_admin_general = bool(
            user.empresa and user.empresa.es_administradora_general
        )

        data.update({
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "empresa_id": user.empresa_id,
            "instalacion_id": user.instalacion_id,
            "sector_id": user.sector_id,
            "es_administradora_general": es_admin_general,
            "solo_enrolamiento": user.solo_enrolamiento,
        })
        return data