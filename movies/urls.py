from django.urls import path
from . import views

urlpatterns = [
    # Movie listing with advanced filtering, pagination, and sorting
    # Supports query parameters: ?search=term&genres=1&genres=2&languages=1&sort=-rating&page=1
    path('', views.movie_list, name='movie_list'),

    # Movie detail page with secure trailer embedding
    path('<int:movie_id>/', views.movie_detail, name='movie_detail'),
    
    # Theater listing for a specific movie
    path('<int:movie_id>/theaters', views.theater_list, name='theater_list'),
    path('<int:movie_id>/theaters/', views.theater_list),
    
    # Seat booking for a specific theater
    path('theater/<int:theater_id>/seats/book/', views.book_seats, name='book_seats'),
    path('payments/<str:booking_reference>/success/', views.payment_success, name='payment_success'),
    path('payments/<str:booking_reference>/cancel/', views.payment_cancel, name='payment_cancel'),
    path('payments/webhooks/stripe/', views.stripe_webhook, name='stripe_webhook'),
]
