"""Приватный API витрины: логин клиента, /me и цены по доступным каналам.

Клиент — не пользователь Django (не staff). Аутентификация — по токену
(Authorization: Bearer <key>). Публичный каталог остаётся прежним; здесь только
приватный слой, который на шаге 4 подключит витрина.
"""
from decimal import Decimal

from drf_spectacular.utils import extend_schema
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .clients import Client, ClientToken
from .models import Product
from .serializers import _money, _per_piece


# ---------------------------------------------------------------------------
# Аутентификация по токену клиента
# ---------------------------------------------------------------------------
class ClientTokenAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        parts = header.split()
        if not parts or parts[0].lower() != self.keyword.lower():
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Некорректный заголовок авторизации.")
        try:
            token = ClientToken.objects.select_related("client").get(key=parts[1])
        except ClientToken.DoesNotExist:
            raise AuthenticationFailed("Неверный или устаревший токен.")
        if not token.client.is_active:
            raise AuthenticationFailed("Учётная запись отключена.")
        return (token.client, token)

    def authenticate_header(self, request):
        return self.keyword


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------
def _client_dict(c):
    return {"email": c.email, "name": c.name, "channels": sorted(c.channels())}


def caller_channels(request):
    """Каналы, доступные вызывающему: аноним — только розница."""
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False) and hasattr(user, "channels"):
        return user.channels()
    return {"individuals"}


def offers_for_channels(product, channels):
    """Предложения/условия товара, ограниченные набором каналов."""
    offers_out, prices = [], []
    for offer in product.offers.all():
        if not offer.is_active:
            continue
        terms = []
        for t in offer.terms.all():
            if not t.is_active or t.channel not in channels:
                continue
            per = _per_piece(t)
            prices.append(per)
            terms.append({
                "channel": t.channel,
                "channel_display": t.get_channel_display(),
                "unit_name": t.unit_name,
                "unit_base_qty": t.unit_base_qty,
                "step": t.step,
                "min_qty": t.min_qty,
                "price": _money(t.price),
                "per_piece": _money(per),
            })
        if not terms:
            continue
        terms.sort(key=lambda x: (x["channel"], Decimal(x["per_piece"])))
        offers_out.append({
            "seller": offer.warehouse.seller.name if offer.warehouse_id else None,
            "in_stock": (offer.stock_qty or 0) > 0,
            "currency": offer.currency,
            "terms": terms,
        })
    return {"price_from": _money(min(prices)) if prices else None, "offers": offers_out}


# ---------------------------------------------------------------------------
# Вью
# ---------------------------------------------------------------------------
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)  # приватный слой (клиенты) — вне контентной схемы
    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""
        client = Client.objects.filter(email__iexact=email, is_active=True).first()
        if client is None or not client.check_password(password):
            return Response({"error": "Неверный email или пароль."}, status=400)
        token = ClientToken.objects.create(client=client)
        return Response({"token": token.key, "client": _client_dict(client)})


class LogoutView(APIView):
    authentication_classes = [ClientTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(exclude=True)  # приватный слой (клиенты) — вне контентной схемы
    def post(self, request):
        if getattr(request, "auth", None) is not None:
            request.auth.delete()
        return Response(status=204)


class MeView(APIView):
    authentication_classes = [ClientTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(exclude=True)  # приватный слой (клиенты) — вне контентной схемы
    def get(self, request):
        return Response(_client_dict(request.user))


class PricingView(APIView):
    """Цены товара по каналам вызывающего (аноним — только розница)."""
    authentication_classes = [ClientTokenAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)  # приватный слой (цены/офферы) — на паузе, вне схемы
    def get(self, request, slug):
        product = get_object_or_404(
            Product.objects.prefetch_related("offers__terms", "offers__warehouse__seller"),
            slug=slug,
        )
        data = offers_for_channels(product, caller_channels(request))
        return Response(data)
