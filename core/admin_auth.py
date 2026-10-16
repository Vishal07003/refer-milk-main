"""
Authentication and Authorization helpers for the DudhDairy / Refer Milk Admin Panel.

Enforces server-side authentication, active user checks, and administrator privileges:
- Staff users (is_staff=True)
- Superusers (is_superuser=True)
- Users with role == 'admin'
All users must have is_active=True and not be soft-deleted.

Ordinary customers and delivery partners are strictly forbidden from accessing the admin panel.
"""

from functools import wraps
from urllib.parse import quote
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache


def is_admin_user(user):
    """
    Returns True only if the user is authenticated, active, not soft-deleted,
    and has admin/staff privileges.
    """
    if not user or not user.is_authenticated:
        return False
    if not getattr(user, "is_active", False):
        return False
    if getattr(user, "is_deleted", False):
        return False
    return bool(
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "role", None) == "admin"
    )


def get_safe_redirect_url(target_url, allowed_hosts=None, fallback="/dairypanel/"):
    """
    Validates a redirect target URL to prevent open redirect vulnerabilities.
    """
    if not target_url or not isinstance(target_url, str):
        return fallback

    # Strip control characters and whitespace
    target_url = target_url.strip()
    if not target_url:
        return fallback

    # Check safe hosts and schemes
    if url_has_allowed_host_and_scheme(
        url=target_url,
        allowed_hosts=allowed_hosts,
        require_https=False,
    ):
        return target_url
    return fallback


def admin_dashboard_required(view_func):
    """
    Decorator for Admin HTML views (e.g., AdminDashboardView).
    - Unauthenticated: redirects to /dairypanel/login/?next=<path>
    - Authenticated non-admin: redirects to /dairypanel/login/?next=<path>&error=unauthorized
    - Adds never_cache headers to prevent back-button caching of sensitive admin pages.
    """
    @wraps(view_func)
    @never_cache
    def _wrapped_view(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            login_url = getattr(settings, "LOGIN_URL", "/dairypanel/login/")
            next_param = quote(request.get_full_path())
            return redirect(f"{login_url}?next={next_param}")

        if not is_admin_user(user):
            login_url = getattr(settings, "LOGIN_URL", "/dairypanel/login/")
            next_param = quote(request.get_full_path())
            return redirect(f"{login_url}?next={next_param}&error=unauthorized")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def admin_api_required(view_func):
    """
    Decorator for Admin JSON API views (/api/admin/*).
    - Unauthenticated: returns JSON 401 with {error, authenticated: False}
    - Authenticated non-admin: returns JSON 403 with {error, authorized: False}
    - Adds never_cache headers so sensitive admin API data is not cached by browsers.
    """
    @wraps(view_func)
    @never_cache
    def _wrapped_view(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return JsonResponse(
                {
                    "error": "Authentication required. Please log in to the admin panel.",
                    "authenticated": False,
                },
                status=401,
            )

        if not is_admin_user(user):
            return JsonResponse(
                {
                    "error": "Permission denied. Administrator privileges required.",
                    "authorized": False,
                },
                status=403,
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view
