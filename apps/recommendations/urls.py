# apps/recommendations/urls.py

from django.urls import path
from .views import (
    GetRecommendationsView,
    QuickRecommendationsView,
    RecommendationFeedbackView,
    TrackProductClickView,
)

app_name = 'recommendations'

urlpatterns = [
    # Get recommendations for analysis
    path(
        'for-analysis/<int:analysis_id>/',
        GetRecommendationsView.as_view(),
        name='for_analysis'
    ),
    
    # Quick recommendations (no analysis)
    path('quick/', QuickRecommendationsView.as_view(), name='quick'),
    
    # Feedback
    path(
        '<int:pk>/feedback/',
        RecommendationFeedbackView.as_view(),
        name='feedback'
    ),
    
    # Track click
    path(
        '<int:pk>/track-click/',
        TrackProductClickView.as_view(),
        name='track_click'
    ),
]