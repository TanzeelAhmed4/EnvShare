from rest_framework.permissions import BasePermission

from .models import ProjectMembership


def can_access_project(user, project):
    if not user or not user.is_authenticated:
        return False
    return project.creator_id == user.pk or ProjectMembership.objects.filter(
        project=project,
        user=user,
    ).exists()


def can_edit_project_data(user, project):
    """Owners and members may edit project data such as variables."""
    return can_access_project(user, project)


class IsProjectCollaborator(BasePermission):
    """Object permission for project data shared with owners and members."""

    def has_object_permission(self, request, view, obj):
        return can_access_project(request.user, obj)


class IsProjectCreator(BasePermission):
    """Only the project creator may manage its membership or settings."""

    def has_object_permission(self, request, view, obj):
        return bool(request.user.is_authenticated and obj.creator_id == request.user.pk)
