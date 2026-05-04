from django.contrib import admin
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.urls import re_path
from movies.admin_dashboard_views import admin_dashboard, admin_dashboard_api
urlpatterns = []

# Vercel may forward /static requests into Django instead of serving them
# from the edge CDN. Keep an explicit fallback route in Django so admin
# assets still resolve regardless of the runtime environment flags.
urlpatterns.append(re_path(r'^static/(?P<path>.*)$', staticfiles_serve, {'insecure': True}))

urlpatterns += [
    path('admin/analytics/', admin_dashboard, name='admin_analytics_dashboard'),
    path('admin/api/analytics/', admin_dashboard_api, name='admin_analytics_dashboard_api'),
    path('admin/', admin.site.urls),
    path('users/', include('users.urls')),
    path('',include('users.urls')),
    path('movies/', include('movies.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
