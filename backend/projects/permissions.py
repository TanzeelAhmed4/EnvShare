from rest_framework.permissions import BasePermission

from .models import ProjectMembership


OWNER = 'owner'
ROLE_PERMISSIONS = {
    OWNER: frozenset({'view', 'view_variables', 'create_variables', 'edit_variables', 'delete_variables', 'import', 'reveal', 'view_audit', 'manage_members', 'assign_admin', 'assign_manager', 'assign_member', 'delete_project'}),
    ProjectMembership.Role.ADMIN: frozenset({'view', 'view_variables', 'create_variables', 'edit_variables', 'delete_variables', 'import', 'reveal', 'view_audit', 'manage_members', 'assign_manager', 'assign_member'}),
    ProjectMembership.Role.MANAGER: frozenset({'view', 'view_variables', 'create_variables', 'edit_variables', 'delete_variables', 'import', 'reveal', 'view_audit'}),
    ProjectMembership.Role.MEMBER: frozenset({'view', 'view_variables', 'view_audit'}),
}


def project_role(user, project):
    if not user or not user.is_authenticated:
        return None
    if project.creator_id == user.pk:
        return OWNER
    return ProjectMembership.objects.filter(project=project, user=user).values_list('role', flat=True).first()


def has_project_permission(user, project, permission):
    return permission in ROLE_PERMISSIONS.get(project_role(user, project), ())


def can_manage_membership(user, project, membership):
    """Apply target-role restrictions after a caller has project access."""
    if membership.project_id != project.pk or membership.user_id == project.creator_id:
        return False
    caller_role = project_role(user, project)
    if caller_role == OWNER:
        return True
    return caller_role == ProjectMembership.Role.ADMIN and membership.role in (
        ProjectMembership.Role.MANAGER,
        ProjectMembership.Role.MEMBER,
    )


def can_access_project(user, project):
    return has_project_permission(user, project, 'view')


def can_edit_project_data(user, project):
    """Compatibility helper for roles allowed to change project data."""
    return has_project_permission(user, project, 'edit_variables')


class IsProjectCollaborator(BasePermission):
    """Object permission for project data shared with owners and members."""

    def has_object_permission(self, request, view, obj):
        return can_access_project(request.user, obj)


class IsProjectCreator(BasePermission):
    """Only the project creator may manage its membership or settings."""

    def has_object_permission(self, request, view, obj):
        return bool(request.user.is_authenticated and obj.creator_id == request.user.pk)
