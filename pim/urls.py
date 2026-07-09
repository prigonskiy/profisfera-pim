from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from catalog.admin_metrics import server_metrics, rebuild_storefront_view
from catalog.tinymce_upload import tinymce_upload
from catalog.api import (
    AudienceViewSet,
    BrandViewSet,
    CategoryViewSet,
    CharacteristicViewSet,
    DirectionViewSet,
    DocumentViewSet,
    ProductViewSet,
)
from catalog.client_api import LoginView, LogoutView, MeView, PricingView

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
    path("rebuild-storefront/", admin.site.admin_view(rebuild_storefront_view), name="rebuild_storefront"),
    # загрузка изображений из TinyMCE (staff-only, проверка внутри view)
    path("tinymce/upload/", tinymce_upload, name="tinymce_upload"),
    path("api/auth/login/", LoginView.as_view(), name="client-login"),
    path("api/auth/logout/", LogoutView.as_view(), name="client-logout"),
    path("api/auth/me/", MeView.as_view(), name="client-me"),
    path("api/products/<slug:slug>/pricing/", PricingView.as_view(), name="product-pricing"),
    # OpenAPI-схема и интерактивная документация (контракт каталога для интеграции)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),  # вход/выход в браузерном API
    path("", RedirectView.as_view(url="/api/", permanent=False)),
]

# Отдача загруженных медиафайлов в режиме разработки.
# На продакшене этим занимается nginx (настроим на этапе деплоя).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
