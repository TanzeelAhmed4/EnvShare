from django.db.models import Count, Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project, ProjectAccessAuditEvent, ProjectMembership
from .permissions import (
    IsProjectCollaborator,
    can_access_project,
    can_manage_membership,
    has_project_permission,
    project_role,
)
from .serializers import (
    AddProjectMemberSerializer,
    ChangeProjectMemberRoleSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
)


def visible_projects_for(user):
    return Project.objects.filter(
        Q(creator=user) | Q(memberships__user=user),
    ).distinct()


class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return visible_projects_for(self.request.user).annotate(
            member_count=Count('memberships', distinct=True),
        )

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)


class ProjectDetailView(generics.RetrieveAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsProjectCollaborator]
    lookup_url_kwarg = 'project_id'

    def get_queryset(self):
        return visible_projects_for(self.request.user).annotate(
            member_count=Count('memberships', distinct=True),
        )


class ProjectMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def get_project(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        if not can_access_project(request.user, project):
            raise PermissionDenied('You do not have access to this project.')
        if not has_project_permission(request.user, project, 'manage_members'):
            raise PermissionDenied('You do not have permission to manage project members.')
        return project

    def get(self, request, project_id):
        project = self.get_project(request, project_id)
        memberships = project.memberships.select_related('user')
        return Response(ProjectMembershipSerializer(memberships, many=True).data)

    def post(self, request, project_id):
        project = self.get_project(request, project_id)
        serializer = AddProjectMemberSerializer(
            data=request.data,
            context={'project': project},
        )
        serializer.is_valid(raise_exception=True)
        role = serializer.validated_data['role']
        assign_permission = 'assign_' + role
        if not has_project_permission(request.user, project, assign_permission):
            raise PermissionDenied('You cannot assign that project role.')
        if serializer.user.pk == request.user.pk and role in (ProjectMembership.Role.ADMIN, ProjectMembership.Role.MANAGER):
            raise PermissionDenied('You cannot promote yourself.')
        with transaction.atomic():
            membership = ProjectMembership.objects.create(
                project=project,
                user=serializer.user,
                added_by=request.user,
                role=role,
            )
            project.save(update_fields=('updated_at',))
            ProjectAccessAuditEvent.objects.create(
                project=project, actor=request.user, actor_username=request.user.get_username(),
                action=ProjectAccessAuditEvent.Action.ROLE_CHANGED,
                target_email=serializer.user.email.strip().lower(), target_username=serializer.user.get_username(),
                role_after=role,
            )
        return Response(
            ProjectMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, project_id, user_id):
        project = get_object_or_404(Project, pk=project_id)
        if not can_access_project(request.user, project):
            raise PermissionDenied('You do not have access to this project.')
        if not has_project_permission(request.user, project, 'manage_members'):
            raise PermissionDenied('You do not have permission to manage project members.')
        if user_id == project.creator_id and project_role(request.user, project) == 'admin':
            raise PermissionDenied('Admins cannot modify the project owner.')
        membership = get_object_or_404(
            ProjectMembership,
            project=project,
            user_id=user_id,
        )
        if not can_manage_membership(request.user, project, membership):
            raise PermissionDenied('Only the project owner can manage Admin memberships.')
        with transaction.atomic():
            ProjectAccessAuditEvent.objects.create(
                project=project, actor=request.user, actor_username=request.user.get_username(),
                action=ProjectAccessAuditEvent.Action.MEMBER_REMOVED,
                target_email=membership.user.email.strip().lower(), target_username=membership.user.get_username(),
                role_before=membership.role,
            )
            membership.delete()
            project.save(update_fields=('updated_at',))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, project_id, user_id):
        project = get_object_or_404(Project, pk=project_id)
        if not can_access_project(request.user, project):
            raise PermissionDenied('You do not have access to this project.')
        if not has_project_permission(request.user, project, 'manage_members'):
            raise PermissionDenied('You do not have permission to manage project members.')
        if user_id == project.creator_id and project_role(request.user, project) == 'admin':
            raise PermissionDenied('Admins cannot modify the project owner.')
        membership = get_object_or_404(ProjectMembership.objects.select_related('user'), project=project, user_id=user_id)
        if not can_manage_membership(request.user, project, membership):
            raise PermissionDenied('Only the project owner can manage Admin memberships.')
        serializer = ChangeProjectMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data['role']
        if not has_project_permission(request.user, project, 'assign_' + new_role):
            raise PermissionDenied('You cannot assign that project role.')
        if membership.user_id == request.user.pk and new_role in (ProjectMembership.Role.ADMIN, ProjectMembership.Role.MANAGER):
            raise PermissionDenied('You cannot promote yourself.')
        old_role = membership.role
        if old_role != new_role:
            with transaction.atomic():
                membership.role = new_role
                membership.save(update_fields=('role',))
                ProjectAccessAuditEvent.objects.create(
                    project=project, actor=request.user, actor_username=request.user.get_username(),
                    action=ProjectAccessAuditEvent.Action.ROLE_CHANGED,
                    target_email=membership.user.email.strip().lower(), target_username=membership.user.get_username(),
                    role_before=old_role, role_after=new_role,
                )
        return Response(ProjectMembershipSerializer(membership).data)


class ProjectDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, project_id):
        project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
        if not has_project_permission(request.user, project, 'delete_project'):
            raise PermissionDenied('Only the project owner can delete this project.')
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
