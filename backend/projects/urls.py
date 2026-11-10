from django.urls import path

from .environment_views import (
    EnvironmentVariableDetailView,
    EnvironmentImportConfirmView,
    EnvironmentImportPreviewView,
    EnvironmentVariableListCreateView,
    EnvironmentVariableRevealView,
    ProjectEnvironmentListView,
)
from .audit_views import ProjectAccessAuditHistoryView, ProjectAuditHistoryView
from .views import ProjectDetailView, ProjectListCreateView, ProjectMemberDetailView, ProjectMembersView
from .views import ProjectDeleteView
from .invitation_views import (
    InvitationAcceptView, InvitationInspectView,
    ProjectInvitationDetailView, ProjectInvitationListCreateView,
)


urlpatterns = [
    path('', ProjectListCreateView.as_view(), name='project-list-create'),
    path('<int:project_id>/', ProjectDetailView.as_view(), name='project-detail'),
    path('<int:project_id>/delete/', ProjectDeleteView.as_view(), name='project-delete'),
    path('<int:project_id>/audit/', ProjectAuditHistoryView.as_view(), name='project-audit-history'),
    path('<int:project_id>/access-audit/', ProjectAccessAuditHistoryView.as_view(), name='project-access-audit-history'),
    path('<int:project_id>/members/', ProjectMembersView.as_view(), name='project-members'),
    path(
        '<int:project_id>/members/<int:user_id>/',
        ProjectMemberDetailView.as_view(),
        name='project-member-detail',
    ),
    path('<int:project_id>/invitations/', ProjectInvitationListCreateView.as_view(), name='project-invitations'),
    path('<int:project_id>/invitations/<int:invitation_id>/', ProjectInvitationDetailView.as_view(), name='project-invitation-detail'),
    path('invitations/inspect/', InvitationInspectView.as_view(), name='invitation-inspect'),
    path('invitations/accept/', InvitationAcceptView.as_view(), name='invitation-accept'),
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
