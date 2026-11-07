from django.urls import path

from .environment_views import (
    EnvironmentVariableDetailView,
    EnvironmentImportConfirmView,
    EnvironmentImportPreviewView,
    EnvironmentVariableListCreateView,
    EnvironmentVariableRevealView,
    ProjectEnvironmentListView,
)
from .audit_views import ProjectAuditHistoryView
from .views import ProjectDetailView, ProjectListCreateView, ProjectMemberDetailView, ProjectMembersView


urlpatterns = [
    path('', ProjectListCreateView.as_view(), name='project-list-create'),
    path('<int:project_id>/', ProjectDetailView.as_view(), name='project-detail'),
    path('<int:project_id>/audit/', ProjectAuditHistoryView.as_view(), name='project-audit-history'),
    path('<int:project_id>/members/', ProjectMembersView.as_view(), name='project-members'),
    path(
        '<int:project_id>/members/<int:user_id>/',
        ProjectMemberDetailView.as_view(),
        name='project-member-detail',
    ),
    path(
        '<int:project_id>/environments/',
        ProjectEnvironmentListView.as_view(),
        name='project-environments',
    ),
    path(
        '<int:project_id>/environments/<int:environment_id>/variables/',
        EnvironmentVariableListCreateView.as_view(),
        name='environment-variable-list-create',
    ),
    path(
        '<int:project_id>/environments/<int:environment_id>/import/preview/',
        EnvironmentImportPreviewView.as_view(),
        name='environment-import-preview',
    ),
    path(
        '<int:project_id>/environments/<int:environment_id>/import/confirm/',
        EnvironmentImportConfirmView.as_view(),
        name='environment-import-confirm',
    ),
    path(
        '<int:project_id>/environments/<int:environment_id>/variables/<int:variable_id>/',
        EnvironmentVariableDetailView.as_view(),
        name='environment-variable-detail',
    ),
    path(
        '<int:project_id>/environments/<int:environment_id>/variables/<int:variable_id>/reveal/',
        EnvironmentVariableRevealView.as_view(),
        name='environment-variable-reveal',
    ),
]
