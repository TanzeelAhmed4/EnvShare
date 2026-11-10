import difflib

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import record_variable_audit
from .encryption import EncryptionError, decrypt_historical_value
from .environment_serializers import EnvironmentVariableSerializer
from .environment_views import encryption_error_response, get_project_environment
from .models import EnvironmentVariable, EnvironmentVariableAuditEvent, EnvironmentVariableVersion
from .permissions import has_project_permission
from .versions import create_variable_version


class VersionMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnvironmentVariableVersion
        fields = (
            'id', 'variable_id_snapshot', 'variable_key', 'version_number',
            'sensitivity', 'action', 'actor_username', 'created_at',
        )
        read_only_fields = fields


def get_current_variable(request, project_id, environment_id, variable_id, permission='view_variables'):
    _project, environment = get_project_environment(
        request, project_id, environment_id, permission,
    )
    variable = get_object_or_404(EnvironmentVariable, pk=variable_id, environment=environment)
    return environment, variable


def get_variable_version(project, environment, variable, version_id):
    return get_object_or_404(
        EnvironmentVariableVersion,
        pk=version_id,
        project=project,
        environment_id_snapshot=environment.pk,
        variable_id_snapshot=variable.pk,
    )


class EnvironmentVariableVersionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, environment_id, variable_id):
        environment, variable = get_current_variable(request, project_id, environment_id, variable_id)
        versions = EnvironmentVariableVersion.objects.filter(
            project_id=environment.project_id,
            environment_id_snapshot=environment.pk,
            variable_id_snapshot=variable.pk,
        )
        return Response(VersionMetadataSerializer(versions, many=True).data)


class EnvironmentVariableVersionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, environment_id, variable_id, version_id):
        environment, variable = get_current_variable(request, project_id, environment_id, variable_id)
        version = get_variable_version(environment.project, environment, variable, version_id)
        return Response(VersionMetadataSerializer(version).data)


class EnvironmentVariableVersionValueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, environment_id, variable_id, version_id):
        environment, variable = get_current_variable(request, project_id, environment_id, variable_id)
        version = get_variable_version(environment.project, environment, variable, version_id)
        if version.sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE and not has_project_permission(
            request.user, environment.project, 'reveal',
        ):
            raise PermissionDenied('You do not have permission to access historical Sensitive values.')
        try:
            plaintext = decrypt_historical_value(version)
        except EncryptionError as error:
            return encryption_error_response(error)
        if version.sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE:
            try:
                with transaction.atomic():
                    record_variable_audit(
                        action=EnvironmentVariableAuditEvent.Action.VERSION_ACCESSED,
                        actor=request.user,
                        environment=environment,
                        variable_id=version.variable_id_snapshot,
                        key=version.variable_key,
                        sensitivity=version.sensitivity,
                        extra_changes={'version': {'before': None, 'after': version.version_number}},
                    )
            except Exception:
                return Response(
                    {'detail': 'The historical value access could not be audited.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response({
            'version_number': version.version_number,
            'key': version.variable_key,
            'sensitivity': version.sensitivity,
            'value': plaintext,
        })


class VersionCompareSerializer(serializers.Serializer):
    left_version_id = serializers.IntegerField(min_value=1)
    right_version_id = serializers.IntegerField(min_value=1)


class EnvironmentVariableVersionCompareView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id, environment_id, variable_id):
        environment, variable = get_current_variable(request, project_id, environment_id, variable_id)
        serializer = VersionCompareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        versions = [
            get_variable_version(environment.project, environment, variable, serializer.validated_data[field])
            for field in ('left_version_id', 'right_version_id')
        ]
        sensitive = any(
            version.sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE
            for version in versions
        )
        if sensitive and not has_project_permission(request.user, environment.project, 'reveal'):
            raise PermissionDenied('You do not have permission to compare historical Sensitive values.')
        try:
            left_value, right_value = (decrypt_historical_value(version) for version in versions)
        except EncryptionError as error:
            return encryption_error_response(error)
        result = {
            'left_version': versions[0].version_number,
            'right_version': versions[1].version_number,
            'sensitive': sensitive,
            'different': left_value != right_value,
        }
        if not sensitive:
            result['diff'] = list(difflib.unified_diff(
                left_value.splitlines(),
                right_value.splitlines(),
                fromfile=f'v{versions[0].version_number}',
                tofile=f'v{versions[1].version_number}',
                lineterm='',
            ))
        else:
            try:
                with transaction.atomic():
                    record_variable_audit(
                        action=EnvironmentVariableAuditEvent.Action.VERSION_COMPARED,
                        actor=request.user,
                        environment=environment,
                        variable_id=variable.pk,
                        key=variable.key,
                        sensitivity=EnvironmentVariable.Sensitivity.SENSITIVE,
                        extra_changes={
                            'versions': {
                                'before': versions[0].version_number,
                                'after': versions[1].version_number,
                            },
                            'different': {'before': None, 'after': result['different']},
                        },
                    )
            except Exception:
                return Response(
                    {'detail': 'The historical comparison could not be audited.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response(result)


class EnvironmentVariableVersionRestoreView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id, environment_id, variable_id, version_id):
        environment, _variable = get_current_variable(
            request, project_id, environment_id, variable_id, 'edit_variables',
        )
        try:
            with transaction.atomic():
                variable = get_object_or_404(
                    EnvironmentVariable.objects.select_for_update(),
                    pk=variable_id,
                    environment=environment,
                )
                version = get_variable_version(environment.project, environment, variable, version_id)
                plaintext = decrypt_historical_value(version)
                old_key, old_sensitivity = variable.key, variable.sensitivity
                restore_serializer = EnvironmentVariableSerializer(
                    variable,
                    data={
                        'key': version.variable_key,
                        'value': plaintext,
                        'sensitivity': version.sensitivity,
                    },
                    partial=True,
                    context={'environment': environment},
                )
                restore_serializer.is_valid(raise_exception=True)
                restored = restore_serializer.save()
                new_version = create_variable_version(
                    variable=restored,
                    action=EnvironmentVariableVersion.Action.RESTORED,
                    actor=request.user,
                    plaintext=plaintext,
                )
                record_variable_audit(
                    action=EnvironmentVariableAuditEvent.Action.RESTORED,
                    actor=request.user,
                    environment=environment,
                    variable_id=restored.pk,
                    key=restored.key,
                    sensitivity=restored.sensitivity,
                    key_before=old_key,
                    sensitivity_before=old_sensitivity,
                    extra_changes={
                        'restored_from': {'before': None, 'after': version.version_number},
                        'version': {'before': None, 'after': new_version.version_number},
                    },
                )
        except EncryptionError as error:
            return encryption_error_response(error)
        except IntegrityError:
            return Response({'detail': 'The variable could not be restored.'}, status=400)
        return Response(EnvironmentVariableSerializer(
            restored, context={'environment': environment},
        ).data)
