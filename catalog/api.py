from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.models import Q
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from .models import Audience, Brand, Category, Characteristic, Direction, Document, Product
from .permissions import IsStaffOrReadOnly
from .serializers import (
    AudienceMenuSerializer,
    AudienceSerializer,
    BrandSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
    CharacteristicSerializer,
    DirectionSerializer,
    DocumentSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
)


def category_with_descendants(category_id):
    """Возвращает id категории и всех вложенных в неё подкатегорий."""
    ids = [category_id]
    frontier = [category_id]
    while frontier:
        children = list(
            Category.objects.filter(parent_id__in=frontier)
            .exclude(id__in=ids)
            .values_list("id", flat=True)
        )
        ids.extend(children)
        frontier = children
    return ids


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Дерево категорий от корней (parent is null) с вложенностью."""
        roots = Category.objects.filter(parent__isnull=True)
        data = CategoryTreeSerializer(roots, many=True, context={"request": request}).data
        return Response(data)


class CharacteristicViewSet(viewsets.ModelViewSet):
    queryset = Characteristic.objects.prefetch_related("options").all()
    serializer_class = CharacteristicSerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "code"


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [IsStaffOrReadOnly]


class AudienceViewSet(viewsets.ModelViewSet):
    queryset = Audience.objects.all()
    serializer_class = AudienceSerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"

    @action(detail=False, methods=["get"])
    def menu(self, request):
        """Все аудитории со вложенными направлениями — готовое дерево для меню."""
        audiences = Audience.objects.prefetch_related("directions").all()
        data = AudienceMenuSerializer(audiences, many=True, context={"request": request}).data
        return Response(data)


class DirectionViewSet(viewsets.ModelViewSet):
    serializer_class = DirectionSerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"

    def get_queryset(self):
        qs = (
            Direction.objects.select_related("audience")
            .order_by("audience__order", "order", "name")
        )
        audience = self.request.query_params.get("audience")
        if audience:
            qs = qs.filter(audience__slug=audience)
        return qs


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "manufacturer_sku", "short_description"]
    ordering_fields = ["name", "created_at", "updated_at"]

    def get_object(self):
        # к товару можно обратиться и по slug, и по внутреннему артикулу sku
        value = self.kwargs[self.lookup_field]
        qs = self.filter_queryset(self.get_queryset())
        obj = get_object_or_404(qs, Q(slug=value) | Q(sku=value))
        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        qs = (
            Product.objects.select_related("brand", "category", "group")
            .prefetch_related(
                "images",
                "documents",
                "audiences",
                "directions",
                "attribute_values__characteristic",
                "attribute_values__value_options",
                "group__levels",
            )
            .all()
        )
        category = self.request.query_params.get("category")
        if category:
            try:
                ids = category_with_descendants(int(category))
                qs = qs.filter(category_id__in=ids)
            except (ValueError, TypeError):
                qs = qs.none()
        brand = self.request.query_params.get("brand")
        if brand:
            qs = qs.filter(brand_id=brand)

        # навигационные фасеты: ?audience=slug[,slug] и ?direction=slug[,slug]
        # внутри одного параметра slug'и работают как ИЛИ, между параметрами — И
        audience = self.request.query_params.get("audience")
        if audience:
            slugs = [s.strip() for s in audience.split(",") if s.strip()]
            qs = qs.filter(audiences__slug__in=slugs).distinct()
        direction = self.request.query_params.get("direction")
        if direction:
            slugs = [s.strip() for s in direction.split(",") if s.strip()]
            qs = qs.filter(directions__slug__in=slugs).distinct()

        # сопоставление с внешними системами (Litics): по коду из 1С
        external_id = self.request.query_params.get("external_id")
        if external_id:
            qs = qs.filter(external_id=external_id)
        external_ids = self.request.query_params.get("external_id__in")
        if external_ids:
            codes = [c.strip() for c in external_ids.split(",") if c.strip()]
            qs = qs.filter(external_id__in=codes)

        # инкрементальная синхронизация: только изменённые после указанного момента
        updated_since = self.request.query_params.get("updated_since")
        if updated_since:
            dt = parse_datetime(updated_since)
            if dt is None:
                raise ParseError(
                    "updated_since должен быть датой-временем ISO 8601, "
                    "напр. 2026-06-10T12:00:00Z (не забудьте URL-кодировать)."
                )
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            qs = qs.filter(updated_at__gte=dt)
        return qs

    @action(
        detail=False,
        methods=["get"],
        url_path=r"by-external-id/(?P<code>[^/]+)",
    )
    def by_external_id(self, request, code=None):
        """Отдать полную карточку товара по коду сопоставления из 1С."""
        product = self.get_queryset().filter(external_id=code).first()
        if product is None:
            raise NotFound("Товар с таким кодом сопоставления не найден.")
        serializer = ProductDetailSerializer(product, context={"request": request})
        return Response(serializer.data)

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        return ProductDetailSerializer
