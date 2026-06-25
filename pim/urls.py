from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from catalog.admin_metrics import server_metrics
from catalog.api import (
    AudienceViewSet,
    BrandViewSet,
    CategoryViewSet,
    CharacteristicViewSet,
    DirectionViewSet,
    DocumentViewSet,
    ProductViewSet,
)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("characteristics", CharacteristicViewSet, basename="characteristic")
router.register("documents", DocumentViewSet, basename="document")
router.register("audiences", AudienceViewSet, basename="audience")
router.register("directions", DirectionViewSet, basename="direction")

urlpatterns = [
    path("admin/", admin.site.urls),
    # staff-only метрики сервера для панели на главной админки
    path("server-metrics/", admin.site.admin_view(server_metrics), name="server_metrics"),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),  # вход/выход в браузерном API
    path("", RedirectView.as_view(url="/api/", permanent=False)),
]

# Отдача загруженных медиафайлов в режиме разработки.
# На продакшене этим занимается nginx (настроим на этапе деплоя).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
