from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse


ADMIN_ANALYTICS_PERMISSION = 'movies.view_bookingbatch'


def user_can_access_admin_analytics(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.has_perm(ADMIN_ANALYTICS_PERMISSION)
    )


def admin_analytics_page_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user_can_access_admin_analytics(request.user):
            raise PermissionDenied("You do not have permission to access admin analytics.")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def admin_analytics_api_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'detail': 'Authentication credentials were not provided.'},
                status=401,
            )
        if not user_can_access_admin_analytics(request.user):
            return JsonResponse(
                {'detail': 'You do not have permission to access this analytics endpoint.'},
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return _wrapped_view
