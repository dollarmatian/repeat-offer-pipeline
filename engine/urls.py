from django.urls import path

from engine import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("rulesets/", views.RulesetListView.as_view(), name="rulesets"),
    path("decisions/", views.DecisionListView.as_view(), name="decisions"),
    path("decisions/<str:reference>/", views.DecisionDetailView.as_view(), name="decision"),
    path("exceptions/", views.ExceptionListView.as_view(), name="exceptions"),
    path("exceptions/<int:pk>/", views.ExceptionDetailView.as_view(), name="exception"),
    path(
        "exceptions/<int:pk>/resolve/",
        views.ExceptionResolveView.as_view(),
        name="exception-resolve",
    ),
    path("metrics/", views.MetricsView.as_view(), name="metrics"),
]
