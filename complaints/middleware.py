import hashlib
import hmac

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


class LoginAttemptRateLimitMiddleware:
    """Limit repeated failed password submissions using a hashed client address."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST" or request.path not in {
            "/accounts/login/", "/api/auth/login/"
        }:
            return None
        key = self._cache_key(request)
        if cache.get(key, 0) >= settings.LOGIN_RATE_LIMIT_ATTEMPTS:
            return HttpResponse(
                "Too many sign-in attempts. Try again later.",
                status=429,
                headers={"Retry-After": str(settings.LOGIN_RATE_LIMIT_SECONDS)},
            )
        request._login_rate_limit_key = key
        return None

    def process_response(self, request, response):
        key = getattr(request, "_login_rate_limit_key", None)
        if key is None:
            return response
        if getattr(response, "data", None) and "token" in response.data:
            cache.delete(key)
            return response
        if response.status_code in {200, 400, 401}:
            cache.set(key, cache.get(key, 0) + 1, timeout=settings.LOGIN_RATE_LIMIT_SECONDS)
        elif response.status_code in {302, 303}:
            cache.delete(key)
        return response

    @staticmethod
    def _cache_key(request):
        address = request.META.get("REMOTE_ADDR", "unknown")
        digest = hmac.new(settings.SECRET_KEY.encode(), address.encode(), hashlib.sha256).hexdigest()
        return f"login-attempts:{digest}"
