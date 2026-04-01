from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

from .models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "empresa",
            "instalacion",
            "sector",
        )


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    model = User

    list_display = (
        "id",
        "username",
        "first_name",
        "last_name",
        "email",
        "role",
        "empresa",
        "instalacion",
        "sector",
        "is_staff",
        "is_active",
        "is_superuser",
    )

    list_filter = (
        "role",
        "empresa",
        "instalacion",
        "sector",
        "is_staff",
        "is_active",
        "is_superuser",
    )

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Información personal", {"fields": ("first_name", "last_name", "email")}),
        ("Información adicional", {"fields": ("role", "empresa", "instalacion", "sector")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Fechas importantes", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username",
                "password1",
                "password2",
                "first_name",
                "last_name",
                "email",
                "role",
                "empresa",
                "instalacion",
                "sector",
                "is_active",
                "is_staff",
                "is_superuser",
            ),
        }),
    )

    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("id",)
    filter_horizontal = ("groups", "user_permissions")