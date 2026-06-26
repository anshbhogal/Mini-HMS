from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/doctor/', views.doctor_dashboard, name='doctor_dashboard'),
    path('dashboard/patient/', views.patient_dashboard, name='patient_dashboard'),
    path('book/<int:slot_id>/', views.book_slot, name='book_slot'),
    path('google/connect/', views.google_connect, name='google_connect'),
    path('google/oauth2callback/', views.google_oauth_callback, name='google_oauth_callback'),
]
