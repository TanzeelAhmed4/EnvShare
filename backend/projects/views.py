from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project, ProjectMembership
from .permissions import IsProjectCollaborator, can_access_project
from .serializers import (
    AddProjectMemberSerializer,
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
        if project.creator_id != request.user.pk:
            raise PermissionDenied('Only the project creator can manage members.')
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
        membership = ProjectMembership.objects.create(
            project=project,
            user=serializer.user,
            added_by=request.user,
        )
        project.save(update_fields=('updated_at',))
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
        if project.creator_id != request.user.pk:
            raise PermissionDenied('Only the project creator can manage members.')
        membership = get_object_or_404(
            ProjectMembership,
            project=project,
            user_id=user_id,
        )
        membership.delete()
        project.save(update_fields=('updated_at',))
        return Response(status=status.HTTP_204_NO_CONTENT)
