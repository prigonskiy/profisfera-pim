from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsStaffOrReadOnly(BasePermission):
    """
    Чтение (GET/HEAD/OPTIONS) — всем без авторизации.
    Запись (POST/PUT/PATCH/DELETE) — только сотрудникам (is_staff),
    аутентифицированным по токену или сессии.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)
