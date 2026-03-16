# apps/skin_analysis/urls.py

from django.urls import path
from .views import (
    AnalyzeSkinView,
    AnalysisDetailView,
    MyAnalysisHistoryView,
    LatestAnalysisView,
)

app_name = 'skin_analysis'

urlpatterns = [
    # Main analysis endpoint
    path('analyze/', AnalyzeSkinView.as_view(), name='analyze'),
    
    # Analysis detail
    path('<int:pk>/', AnalysisDetailView.as_view(), name='detail'),
    
    # User history
    path('my-history/', MyAnalysisHistoryView.as_view(), name='my_history'),
    path('latest/', LatestAnalysisView.as_view(), name='latest'),
]