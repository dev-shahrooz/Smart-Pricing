from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('bom-upload/', views.bom_upload_view, name='bom_upload'),
    path('pricing-form/', views.pricing_form_view, name='pricing_form'),
    path('scenario/', views.scenario_view, name='scenario'),
    path('ai-insights/', views.ai_insights_view, name='ai_insights'),
]
