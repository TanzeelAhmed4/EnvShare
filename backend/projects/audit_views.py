from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404

from .models import EnvironmentVariableAuditEvent, ProjectAccessAuditEvent
from .views import visible_projects_for
from .permissions import has_project_permission
from rest_framework.exceptions import PermissionDenied


ENVIRONMENT_LABELS = {
    'development': 'Development',
    'staging': 'Staging',
    'production': 'Production',
}


class EnvironmentVariableAuditSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source='actor_username', read_only=True)
    action_label = serializers.CharField(source='get_action_display', read_only=True)
    environment_label = serializers.SerializerMethodField()

    class Meta:
        model = EnvironmentVariableAuditEvent
        fields = (
            'id', 'project_name', 'environment_name', 'environment_label',
            'variable_id', 'variable_key', 'action', 'action_label',
            'actor', 'changes', 'created_at',
        )
        read_only_fields = fields

    def get_environment_label(self, instance):
        return ENVIRONMENT_LABELS.get(instance.environment_name, instance.environment_name)


class ProjectAuditHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
        if not has_project_permission(request.user, project, 'view_audit'):
            raise PermissionDenied('You do not have permission to view this project history.')
        events = EnvironmentVariableAuditEvent.objects.filter(project=project).order_by('-created_at', '-pk')
        return Response(EnvironmentVariableAuditSerializer(events, many=True).data)


class ProjectAccessAuditHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
        if not has_project_permission(request.user, project, 'view_audit'):
            raise PermissionDenied('You do not have permission to view this project history.')
        events = ProjectAccessAuditEvent.objects.filter(project=project).values(
            'id', 'actor_username', 'action', 'target_email', 'target_username',
            'role_before', 'role_after', 'created_at',
        )
        return Response(list(events))
