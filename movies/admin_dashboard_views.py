from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.http import JsonResponse
from django.shortcuts import render

from .analytics import get_admin_dashboard_analytics


@staff_member_required
@permission_required('movies.view_bookingbatch', raise_exception=True)
def admin_dashboard(request):
    analytics = get_admin_dashboard_analytics()
    return render(request, 'admin/analytics_dashboard.html', {'analytics': analytics})


@staff_member_required
@permission_required('movies.view_bookingbatch', raise_exception=True)
def admin_dashboard_api(request):
    analytics = get_admin_dashboard_analytics()
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
    }
    return JsonResponse(serializable)
