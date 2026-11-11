from datetime import datetime, time, timedelta

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Environment, EnvironmentVariableAuditEvent, ProjectAccessAuditEvent
from .permissions import has_project_permission
from .views import visible_projects_for


ENVIRONMENT_LABELS = {
    'development': 'Development',
    'staging': 'Staging',
    'production': 'Production',
}


class EnvironmentVariableAuditSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source='actor_username', read_only=True)
    action_label = serializers.SerializerMethodField()
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

    def get_action_label(self, instance):
        if instance.changes.get('source', {}).get('after') == 'bulk_import':
            return 'Bulk import'
        return instance.get_action_display()


class AuditPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'results': data,
        })


def _positive_int(params, name, default=None, maximum=None):
    value = params.get(name)
    if value in (None, ''):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: 'Enter a positive integer.'}) from None
    if parsed < 1 or (maximum is not None and parsed > maximum):
        raise ValidationError({name: 'Enter a valid positive integer.'})
    return parsed


def _date_boundary(params, name, *, end=False):
    value = params.get(name)
    if value in (None, ''):
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise ValidationError({name: 'Use an ISO date in YYYY-MM-DD format.'})
    boundary_date = parsed + timedelta(days=1) if end else parsed
    boundary = datetime.combine(boundary_date, time.min)
    return timezone.make_aware(boundary, timezone.get_current_timezone())


def _pagination(request):
    page = _positive_int(request.query_params, 'page', default=1)
    page_size = _positive_int(request.query_params, 'page_size', default=20, maximum=100)
    return page, page_size


def _paginated(request, queryset, serializer_class):
    page, page_size = _pagination(request)
    paginator = AuditPagination()
    paginator.page_size = page_size
    page_items = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(serializer_class(page_items, many=True).data)


class ProjectAuditHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
        if not has_project_permission(request.user, project, 'view_audit'):
            raise PermissionDenied('You do not have permission to view this project history.')
        params = request.query_params
        page, page_size = _pagination(request)
        del page, page_size
        valid_actions = (
            {value for value, _ in EnvironmentVariableAuditEvent.Action.choices}
            | {value for value, _ in ProjectAccessAuditEvent.Action.choices}
        )
        action = params.get('action')
        if action and action not in valid_actions:
            raise ValidationError({'action': 'Choose a valid audit action.'})
        environment_id = _positive_int(params, 'environment')
        if environment_id is not None and not Environment.objects.filter(pk=environment_id, project=project).exists():
            raise ValidationError({'environment': 'Choose an environment in this project.'})
        actor = params.get('actor', '').strip()
        if len(actor) > 150:
            raise ValidationError({'actor': 'Actor filter is too long.'})
        variable_id = _positive_int(params, 'variable_id')
        variable_key = params.get('variable_key', '').strip()
        search = params.get('search', '').strip()
        if len(variable_key) > 255 or len(search) > 200:
            raise ValidationError({'search': 'Search filters are too long.'})
        date_from = _date_boundary(params, 'date_from')
        date_to = _date_boundary(params, 'date_to', end=True)
        if date_from and date_to and date_from >= date_to:
            raise ValidationError({'date_to': 'End date must be on or after start date.'})

        events = EnvironmentVariableAuditEvent.objects.filter(project=project)
        if action:
            if action == 'bulk_imported':
                events = events.filter(changes__source__after='bulk_import')
            elif action in {value for value, _ in EnvironmentVariableAuditEvent.Action.choices}:
                events = events.filter(action=action)
            else:
                events = events.none()
        if environment_id:
            events = events.filter(environment_id=environment_id)
        if actor:
            events = events.filter(actor_username=actor)
        if variable_id:
            events = events.filter(variable_id=variable_id)
        if variable_key:
            events = events.filter(variable_key=variable_key)
        if date_from:
            events = events.filter(created_at__gte=date_from)
        if date_to:
            events = events.filter(created_at__lt=date_to)
        if search:
            events = events.filter(
                Q(variable_key__icontains=search)
                | Q(actor_username__icontains=search)
                | Q(action__icontains=search)
            )
        return _paginated(request, events.order_by('-created_at', '-pk'), EnvironmentVariableAuditSerializer)


class AccessAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectAccessAuditEvent
        fields = (
            'id', 'actor_username', 'action', 'target_email', 'target_username',
            'role_before', 'role_after', 'created_at',
        )
        read_only_fields = fields


class ProjectAccessAuditHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
        if not has_project_permission(request.user, project, 'view_audit'):
            raise PermissionDenied('You do not have permission to view this project history.')
        params = request.query_params
        _pagination(request)
        action = params.get('action', '').strip()
        valid_actions = (
            {value for value, _ in ProjectAccessAuditEvent.Action.choices}
            | {value for value, _ in EnvironmentVariableAuditEvent.Action.choices}
        )
        if action and action not in valid_actions:
            raise ValidationError({'action': 'Choose a valid audit action.'})
        actor = params.get('actor', '').strip()
        search = params.get('search', '').strip()
        if len(actor) > 150 or len(search) > 200:
            raise ValidationError({'search': 'Search filters are too long.'})
        date_from = _date_boundary(params, 'date_from')
        date_to = _date_boundary(params, 'date_to', end=True)
        if date_from and date_to and date_from >= date_to:
            raise ValidationError({'date_to': 'End date must be on or after start date.'})
        events = ProjectAccessAuditEvent.objects.filter(project=project)
        if action:
            if action in {value for value, _ in ProjectAccessAuditEvent.Action.choices}:
                events = events.filter(action=action)
            else:
                events = events.none()
        if actor:
            events = events.filter(actor_username=actor)
        if date_from:
            events = events.filter(created_at__gte=date_from)
        if date_to:
            events = events.filter(created_at__lt=date_to)
        if search:
            events = events.filter(
                Q(actor_username__icontains=search)
                | Q(target_username__icontains=search)
                | Q(target_email__icontains=search)
                | Q(action__icontains=search)
            )
        return _paginated(request, events.order_by('-created_at', '-pk'), AccessAuditSerializer)
