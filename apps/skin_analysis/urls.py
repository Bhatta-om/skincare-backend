# apps/skin_analysis/urls.py  — REPLACE your current file with this
from django.urls import path
from .views import (
    AnalyzeSkinView,
    AnalysisDetailView,
    MyAnalysisHistoryView,
    LatestAnalysisView,
    AdminSkinAnalysisView,   # ← new
)

app_name = 'skin_analysis'

urlpatterns = [
    path('analyze/',     AnalyzeSkinView.as_view(),        name='analyze'),
    path('<int:pk>/',    AnalysisDetailView.as_view(),      name='detail'),
    path('my-history/',  MyAnalysisHistoryView.as_view(),   name='my_history'),
    path('latest/',      LatestAnalysisView.as_view(),      name='latest'),
    path('admin/all/',   AdminSkinAnalysisView.as_view(),   name='admin_all'),   # ← new
]