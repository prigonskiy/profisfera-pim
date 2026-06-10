from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Brand, Category, Characteristic, Document, Product
from .permissions import IsStaffOrReadOnly
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
    CharacteristicSerializer,
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


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "manufacturer_sku", "short_description"]
    ordering_fields = ["name", "created_at", "updated_at"]

    def get_queryset(self):
        qs = (
            Product.objects.select_related("brand", "category")
            .prefetch_related(
                "images",
                "documents",
                "attribute_values__characteristic",
                "attribute_values__value_options",
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
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        return ProductDetailSerializer
