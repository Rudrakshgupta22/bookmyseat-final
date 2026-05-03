from django.http import JsonResponse
from django.shortcuts import render
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_GET

from .admin_access import admin_analytics_api_required, admin_analytics_page_required
from .analytics import get_admin_dashboard_analytics


@require_GET
@admin_analytics_page_required
def admin_dashboard(request):
    analytics = get_admin_dashboard_analytics(force_refresh=request.GET.get('fresh') == '1')
    response = render(
        request,
        'admin/analytics_dashboard.html',
        {
            'analytics': analytics,
        },
    )
    add_never_cache_headers(response)
    return response


@require_GET
@admin_analytics_api_required
def admin_dashboard_api(request):
    analytics = get_admin_dashboard_analytics(force_refresh=request.GET.get('fresh') == '1')
    serializable = {
        'revenue': analytics['revenue'],
        'popular_movies': analytics['popular_movies'],
        'busiest_theaters': [
            {
                **item,
                'occupancy_rate': float(item['occupancy_rate']),
            }
            for item in analytics['busiest_theaters']
        ],
        'peak_booking_hours': analytics['peak_booking_hours'],
        'cancellation': analytics['cancellation'],
        'generated_at': analytics['generated_at'].isoformat(),
        'refresh_interval_seconds': analytics['refresh_interval_seconds'],
        'cache_backend': analytics['cache_backend'],
    }
    response = JsonResponse(serializable)
    add_never_cache_headers(response)
    return response
