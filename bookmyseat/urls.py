from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from movies.admin_dashboard_views import admin_dashboard, admin_dashboard_api
urlpatterns = [
    path('admin/analytics/', admin_dashboard, name='admin_analytics_dashboard'),
    path('admin/api/analytics/', admin_dashboard_api, name='admin_analytics_dashboard_api'),
    path('admin/', admin.site.urls),
    path('users/', include('users.urls')),
    path('',include('users.urls')),
    path('movies/', include('movies.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if getattr(settings, 'IS_VERCEL', False):
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT, insecure=True)
