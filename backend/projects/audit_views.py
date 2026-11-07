from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404

from .models import EnvironmentVariableAuditEvent
from .views import visible_projects_for


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
        events = EnvironmentVariableAuditEvent.objects.filter(project=project).order_by('-created_at', '-pk')
        return Response(EnvironmentVariableAuditSerializer(events, many=True).data)
