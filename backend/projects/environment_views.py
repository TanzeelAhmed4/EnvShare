import hashlib
import hmac
import json

from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import _MISSING, record_variable_audit
from .encryption import EncryptionError, decrypt_value, encrypt_value
from .env_import import parse_env_content
from .environment_serializers import EnvironmentSerializer, EnvironmentVariableSerializer
from .models import Environment, EnvironmentVariable, EnvironmentVariableAuditEvent
from .permissions import has_project_permission
from .views import visible_projects_for


def get_project_environment(request, project_id, environment_id=None, permission='view_variables'):
    project = get_object_or_404(visible_projects_for(request.user), pk=project_id)
    if not has_project_permission(request.user, project, permission):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied('You do not have permission to perform this project action.')
    if environment_id is None:
        return project, None
    environment = get_object_or_404(Environment, pk=environment_id, project=project)
    return project, environment


def encryption_error_response(error):
    return Response({'detail': str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class ProjectEnvironmentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project, _ = get_project_environment(request, project_id, permission='view_variables')
        environments = project.environments.order_by('pk')
        return Response(EnvironmentSerializer(environments, many=True).data)


class EnvironmentVariableListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, environment_id):
        _project, environment = get_project_environment(request, project_id, environment_id, 'view_variables')
        variables = environment.variables.all()
        return Response(EnvironmentVariableSerializer(
            variables,
            many=True,
            context={'environment': environment},
        ).data)

    def post(self, request, project_id, environment_id):
        _project, environment = get_project_environment(request, project_id, environment_id, 'create_variables')
        serializer = EnvironmentVariableSerializer(
            data=request.data,
            context={'environment': environment},
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                variable = serializer.save(environment=environment)
                record_variable_audit(
                    action='created',
                    actor=request.user,
                    environment=environment,
                    variable_id=variable.pk,
                    key=variable.key,
                    sensitivity=variable.sensitivity,
                    value_after=variable.value,
                )
        except EncryptionError as error:
            return encryption_error_response(error)
        except IntegrityError:
            return Response(
                {'detail': 'The variable and its audit record could not be saved.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            EnvironmentVariableSerializer(variable, context={'environment': environment}).data,
            status=status.HTTP_201_CREATED,
        )


class EnvironmentVariableDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_variable(self, request, project_id, environment_id, variable_id):
        _project, environment = get_project_environment(request, project_id, environment_id, 'view_variables')
        variable = get_object_or_404(
            EnvironmentVariable,
            pk=variable_id,
            environment=environment,
        )
        return environment, variable

    def get(self, request, project_id, environment_id, variable_id):
        environment, variable = self.get_variable(request, project_id, environment_id, variable_id)
        return Response(EnvironmentVariableSerializer(
            variable,
            context={'environment': environment},
        ).data)

    def patch(self, request, project_id, environment_id, variable_id):
        _project, environment = get_project_environment(request, project_id, environment_id, 'edit_variables')
        variable = get_object_or_404(EnvironmentVariable, pk=variable_id, environment=environment)
        serializer = EnvironmentVariableSerializer(
            variable,
            data=request.data,
            partial=True,
            context={'environment': environment},
        )
        serializer.is_valid(raise_exception=True)
        old_key = variable.key
        old_sensitivity = variable.sensitivity
        old_value = variable.value
        new_sensitivity = serializer.validated_data.get('sensitivity', old_sensitivity)
        include_value = 'value' in serializer.validated_data or new_sensitivity != old_sensitivity
        try:
            with transaction.atomic():
                updated = serializer.save()
                record_variable_audit(
                    action='updated',
                    actor=request.user,
                    environment=environment,
                    variable_id=updated.pk,
                    key=updated.key,
                    sensitivity=updated.sensitivity,
                    key_before=old_key,
                    sensitivity_before=old_sensitivity,
                    value_before=old_value if include_value else _MISSING,
                    value_after=updated.value if include_value else _MISSING,
                    sensitivity_before_for_value=old_sensitivity,
                    sensitivity_after_for_value=updated.sensitivity,
                )
        except EncryptionError as error:
            return encryption_error_response(error)
        except IntegrityError:
            return Response(
                {'detail': 'The variable update and its audit record could not be saved.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(EnvironmentVariableSerializer(
            updated,
            context={'environment': environment},
        ).data)

    def delete(self, request, project_id, environment_id, variable_id):
        _project, environment = get_project_environment(request, project_id, environment_id, 'delete_variables')
        variable = get_object_or_404(EnvironmentVariable, pk=variable_id, environment=environment)
        with transaction.atomic():
            record_variable_audit(
                action='deleted',
                actor=request.user,
                environment=environment,
                variable_id=variable.pk,
                key=variable.key,
                sensitivity=variable.sensitivity,
                value_before=variable.value,
            )
            variable.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EnvironmentVariableRevealView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id, environment_id, variable_id):
        _project, environment = get_project_environment(request, project_id, environment_id, 'reveal')
        variable = get_object_or_404(EnvironmentVariable, pk=variable_id, environment=environment)
        if variable.sensitivity != EnvironmentVariable.Sensitivity.SENSITIVE:
            return Response(
                {'detail': 'Only Sensitive variables have a reveal operation.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            plaintext = decrypt_value(variable.value, environment, variable.key)
        except EncryptionError as error:
            return encryption_error_response(error)

        try:
            with transaction.atomic():
                record_variable_audit(
                    action=EnvironmentVariableAuditEvent.Action.REVEALED,
                    actor=request.user,
                    environment=environment,
                    variable_id=variable.pk,
                    key=variable.key,
                    sensitivity=variable.sensitivity,
                )
        except Exception:
            # A reveal is successful only when its audit event is persisted.
            # Do not include exception details, which could expose data.
            return Response(
                {'detail': 'The variable reveal could not be audited.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({'key': variable.key, 'value': plaintext})


MASKED_IMPORT_VALUE = '••••••••'


def import_request_data(request):
    content = request.data.get('content')
    classifications = request.data.get('classifications', {})
    if not isinstance(content, str):
        return None, None, Response({'content': ['Provide .env text to import.']}, status=400)
    if len(content) > 1_000_000:
        return None, None, Response({'content': ['The pasted content is too large.']}, status=400)
    if not isinstance(classifications, dict):
        return None, None, Response({'classifications': ['Expected an object of key-to-classification values.']}, status=400)
    allowed = {choice for choice, _label in EnvironmentVariable.Sensitivity.choices}
    if any(not isinstance(value, str) or value not in allowed for value in classifications.values()):
        return None, None, Response({'classifications': ['Choose Standard or Sensitive for each new variable.']}, status=400)
    return content, classifications, None


IMPORT_PREVIEW_SALT = 'envshare.import-preview.v1'
IMPORT_PREVIEW_MAX_AGE = 15 * 60


def import_state_fingerprint(environment, actor, content, classifications, entries, existing):
    """Return a keyed fingerprint; neither imported nor stored values enter the signed token."""
    keys = sorted(entry['key'] for entry in entries)
    state = [
        (key, existing[key].sensitivity, existing[key].value)
        for key in keys if key in existing
    ]
    snapshot = json.dumps({
        'project_id': environment.project_id,
        'environment_id': environment.pk,
        'actor_id': actor.pk,
        'content': content,
        'classifications': sorted(classifications.items()),
        'existing': state,
    }, ensure_ascii=True, separators=(',', ':'), sort_keys=True)
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        snapshot.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def import_preview(environment, entries, classifications, existing=None):
    if existing is None:
        existing = {item.key: item for item in environment.variables.all()}
    preview = []
    for entry in entries:
        key, value = entry['key'], entry['value']
        current = existing.get(key)
        if current is None:
            sensitivity = classifications.get(key)
            preview.append({
                'classification': 'New',
                'key': key,
                'old_value': None,
                'new_value': value if sensitivity == EnvironmentVariable.Sensitivity.STANDARD else MASKED_IMPORT_VALUE,
                'sensitivity': sensitivity,
            })
            continue

        sensitive = current.sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE
        old_value = MASKED_IMPORT_VALUE if sensitive else current.value
        changed = old_value != value if not sensitive else True
        # Sensitive values are compared only after decryption, but never returned to the client.
        if sensitive:
            try:
                changed = decrypt_value(current.value, environment, key) != value
            except EncryptionError:
                return None, encryption_error_response(EncryptionError('Sensitive value could not be compared.'))
        if not changed:
            classification = 'Unchanged'
        else:
            classification = 'Update'
        preview.append({
            'classification': classification,
            'key': key,
            'old_value': old_value,
            'new_value': MASKED_IMPORT_VALUE if sensitive else value,
            'sensitivity': current.sensitivity,
        })
    return preview, None


class EnvironmentImportPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id, environment_id):
        _project, environment = get_project_environment(request, project_id, environment_id, 'import')
        content, classifications, error = import_request_data(request)
        if error:
            return error
        entries, errors = parse_env_content(content)
        entry_keys = {entry['key'] for entry in entries}
        if set(classifications) - entry_keys:
            return Response({'classifications': ['Classification choices must match imported keys.']}, status=400)
        with transaction.atomic():
            keys = [entry['key'] for entry in entries]
            existing = {
                item.key: item for item in EnvironmentVariable.objects.filter(
                    environment=environment,
                    key__in=keys,
                ).select_for_update()
            }
            preview, preview_error = import_preview(environment, entries, classifications, existing)
            if preview_error:
                return preview_error
            fingerprint = import_state_fingerprint(
                environment, request.user, content, classifications, entries, existing,
            )
            preview_token = signing.dumps({
                'project_id': environment.project_id,
                'environment_id': environment.pk,
                'actor_id': request.user.pk,
                'fingerprint': fingerprint,
            }, salt=IMPORT_PREVIEW_SALT, compress=True)
        return Response({
            'preview': preview,
            'invalid_lines': errors,
            'preview_token': preview_token,
        })


class EnvironmentImportConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id, environment_id):
        _project, environment = get_project_environment(request, project_id, environment_id, 'import')
        if request.data.get('confirm') is not True:
            return Response({'detail': 'Confirm the import after reviewing its preview.'}, status=400)
        content, classifications, error = import_request_data(request)
        if error:
            return error
        entries, errors = parse_env_content(content)
        if errors:
            return Response({'detail': 'Fix invalid lines before confirming the import.', 'invalid_lines': errors}, status=400)

        allowed = {choice for choice, _label in EnvironmentVariable.Sensitivity.choices}
        unknown_classifications = set(classifications) - {entry['key'] for entry in entries}
        if unknown_classifications or any(value not in allowed for value in classifications.values()):
            return Response({'classifications': ['Classification choices must match imported keys.']}, status=400)

        try:
            signed_preview = signing.loads(
                request.data.get('preview_token', ''),
                salt=IMPORT_PREVIEW_SALT,
                max_age=IMPORT_PREVIEW_MAX_AGE,
            )
        except (BadSignature, SignatureExpired, TypeError):
            return Response(
                {'detail': 'Import preview is invalid or expired. Preview the changes again.'},
                status=status.HTTP_409_CONFLICT,
            )
        if any(signed_preview.get(field) != expected for field, expected in (
            ('project_id', environment.project_id),
            ('environment_id', environment.pk),
            ('actor_id', request.user.pk),
        )):
            return Response(
                {'detail': 'Import preview is invalid or expired. Preview the changes again.'},
                status=status.HTTP_409_CONFLICT,
            )

        created = updated = unchanged = 0
        try:
            with transaction.atomic():
                keys = [entry['key'] for entry in entries]
                existing = {
                    item.key: item for item in EnvironmentVariable.objects.filter(
                        environment=environment,
                        key__in=keys,
                    ).select_for_update()
                }
                new_keys = {entry['key'] for entry in entries} - set(existing)
                if new_keys - set(classifications):
                    return Response({'classifications': ['Choose a classification for every new variable.']}, status=400)
                current_fingerprint = import_state_fingerprint(
                    environment, request.user, content, classifications, entries, existing,
                )
                if not hmac.compare_digest(current_fingerprint, signed_preview.get('fingerprint', '')):
                    return Response(
                        {'detail': 'Environment variables changed after preview. Preview the changes again.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                for entry in entries:
                    key, plaintext = entry['key'], entry['value']
                    variable = existing.get(key)
                    if variable is None:
                        sensitivity = classifications[key]
                        stored = encrypt_value(plaintext, environment, key) if sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE else plaintext
                        variable = EnvironmentVariable.objects.create(
                            environment=environment,
                            key=key,
                            value=stored,
                            sensitivity=sensitivity,
                        )
                        existing[key] = variable
                        record_variable_audit(
                            action='created',
                            actor=request.user,
                            environment=environment,
                            variable_id=variable.pk,
                            key=variable.key,
                            sensitivity=variable.sensitivity,
                            value_after=variable.value,
                        )
                        created += 1
                    else:
                        old_plaintext = (
                            decrypt_value(variable.value, environment, key)
                            if variable.sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE
                            else variable.value
                        )
                        if old_plaintext == plaintext:
                            unchanged += 1
                            continue
                        before_value = variable.value
                        variable.value = (
                            encrypt_value(plaintext, environment, key)
                            if variable.sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE
                            else plaintext
                        )
                        variable.save(update_fields=['value', 'updated_at'])
                        record_variable_audit(
                            action='updated',
                            actor=request.user,
                            environment=environment,
                            variable_id=variable.pk,
                            key=variable.key,
                            sensitivity=variable.sensitivity,
                            value_before=before_value,
                            value_after=variable.value,
                            sensitivity_before_for_value=variable.sensitivity,
                            sensitivity_after_for_value=variable.sensitivity,
                        )
                        updated += 1
        except EncryptionError as encryption_error:
            return encryption_error_response(encryption_error)
        except IntegrityError:
            return Response({'detail': 'The import and its audit records could not be saved.'}, status=400)
        return Response({'created': created, 'updated': updated, 'unchanged': unchanged}, status=200)
