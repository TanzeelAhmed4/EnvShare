import base64
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .encryption import EncryptionError, decrypt_historical_value
from .models import (
    Environment,
    EnvironmentVariable,
    EnvironmentVariableAuditEvent,
    EnvironmentVariableVersion,
    Project,
    ProjectMembership,
)

User = get_user_model()
TEST_KEY = base64.urlsafe_b64encode(b'V' * 32).decode('ascii')


@override_settings(ENVSHARE_ENCRYPTION_KEY=TEST_KEY)
class EnvironmentVariableVersionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='version-owner', email='v-owner@example.test')
        self.manager = User.objects.create_user(username='version-manager', email='v-manager@example.test')
        self.member = User.objects.create_user(username='version-member', email='v-member@example.test')
        self.outsider = User.objects.create_user(username='version-outsider', email='v-outsider@example.test')
        self.project = Project.objects.create(name='Version project', creator=self.owner)
        ProjectMembership.objects.create(project=self.project, user=self.manager, added_by=self.owner, role='manager')
        ProjectMembership.objects.create(project=self.project, user=self.member, added_by=self.owner, role='member')
        self.environment = self.project.environments.get(name=Environment.Name.DEVELOPMENT)
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def variables_url(self):
        return f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/variables/'

    def versions_url(self, variable):
        return f'{self.variables_url()}{variable.pk}/versions/'

    def create_variable(self, key='SERVICE_URL', value='https://one.example', sensitivity='standard', user=None):
        self.authenticate(user or self.owner)
        response = self.client.post(
            self.variables_url(), {'key': key, 'value': value, 'sensitivity': sensitivity}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return EnvironmentVariable.objects.get(pk=response.json()['id'])

    def update(self, variable, payload, user=None):
        self.authenticate(user or self.owner)
        return self.client.patch(f'{self.variables_url()}{variable.pk}/', payload, format='json')

    def test_create_update_noop_key_and_classification_changes_capture_encrypted_snapshots(self):
        value = 'first-standard-value-unique'
        variable = self.create_variable(value=value)
        first = EnvironmentVariableVersion.objects.get(variable=variable)
        self.assertEqual((first.version_number, first.action, first.variable_key, first.sensitivity), (1, 'created', 'SERVICE_URL', 'standard'))
        self.assertTrue(first.encrypted_value.startswith('aesgcm:v1:'))
        self.assertNotIn(value, first.encrypted_value)
        self.assertEqual(decrypt_historical_value(first), value)

        self.assertEqual(self.update(variable, {'value': value}).status_code, 200)
        self.assertEqual(EnvironmentVariableVersion.objects.filter(variable_id_snapshot=variable.pk).count(), 1)
        self.assertEqual(self.update(variable, {'value': 'second-value'}).status_code, 200)
        self.assertEqual(self.update(variable, {'key': 'RENAMED_URL'}).status_code, 200)
        self.assertEqual(self.update(variable, {'sensitivity': 'sensitive'}).status_code, 200)
        versions = list(EnvironmentVariableVersion.objects.filter(variable_id_snapshot=variable.pk).order_by('version_number'))
        self.assertEqual([item.version_number for item in versions], [1, 2, 3, 4])
        self.assertEqual([(item.variable_key, item.sensitivity) for item in versions], [
            ('SERVICE_URL', 'standard'), ('SERVICE_URL', 'standard'),
            ('RENAMED_URL', 'standard'), ('RENAMED_URL', 'sensitive'),
        ])
        self.assertEqual(decrypt_historical_value(versions[1]), 'second-value')
        self.assertEqual(decrypt_historical_value(versions[2]), 'second-value')
        self.assertEqual(decrypt_historical_value(versions[3]), 'second-value')
        nonces = [item.encrypted_value.removeprefix('aesgcm:v1:')[:16] for item in versions]
        self.assertEqual(len(set(nonces)), len(nonces))

    def test_sensitive_history_is_encrypted_masked_and_audited_before_reveal(self):
        secret = 'historical-sensitive-marker'
        variable = self.create_variable(key='PRIVATE', value=secret, sensitivity='sensitive')
        version = EnvironmentVariableVersion.objects.get(variable=variable)
        self.assertNotIn(secret, version.encrypted_value)
        self.authenticate(self.member)
        metadata = self.client.get(self.versions_url(variable))
        self.assertEqual(metadata.status_code, 200)
        self.assertNotIn(secret, metadata.content.decode())
        value_url = f'{self.versions_url(variable)}{version.pk}/value/'
        self.assertEqual(self.client.get(value_url).status_code, 403)
        self.authenticate(self.manager)
        revealed = self.client.get(value_url)
        self.assertEqual(revealed.status_code, 200)
        self.assertEqual(revealed.json()['value'], secret)
        event = EnvironmentVariableAuditEvent.objects.get(action='version_accessed')
        self.assertEqual(event.changes, {'version': {'before': None, 'after': 1}})
        self.assertNotIn(secret, str(event.changes))

    def test_wrong_historical_context_fails_authentication(self):
        variable = self.create_variable(key='CONTEXT_KEY', value='context-bound')
        version = EnvironmentVariableVersion.objects.get(variable=variable)
        version.variable_key = 'SUBSTITUTED_KEY'
        with self.assertRaises(EncryptionError):
            decrypt_historical_value(version)
        version.refresh_from_db()
        version.version_number += 1
        with self.assertRaises(EncryptionError):
            decrypt_historical_value(version)

    def test_standard_comparison_returns_diff_sensitive_comparison_only_metadata(self):
        variable = self.create_variable(value='alpha\nkeep')
        first = EnvironmentVariableVersion.objects.get(variable=variable)
        self.update(variable, {'value': 'beta\nkeep'})
        second = EnvironmentVariableVersion.objects.filter(variable=variable).order_by('-version_number').first()
        compare_url = f'{self.versions_url(variable)}compare/'
        self.authenticate(self.member)
        same = self.client.post(compare_url, {'left_version_id': first.pk, 'right_version_id': first.pk}, format='json')
        self.assertEqual(same.status_code, 200)
        self.assertFalse(same.json()['different'])
        compared = self.client.post(compare_url, {'left_version_id': first.pk, 'right_version_id': second.pk}, format='json')
        self.assertEqual(compared.status_code, 200)
        self.assertTrue(compared.json()['different'])
        self.assertTrue(any(line.startswith('-alpha') for line in compared.json()['diff']))
        self.assertTrue(any(line.startswith('+beta') for line in compared.json()['diff']))

        secret_variable = self.create_variable(key='SECRET_COMPARE', value='secret-one', sensitivity='sensitive')
        secret_first = EnvironmentVariableVersion.objects.get(variable=secret_variable)
        self.update(secret_variable, {'value': 'secret-two'})
        secret_second = EnvironmentVariableVersion.objects.filter(variable=secret_variable).order_by('-version_number').first()
        self.authenticate(self.member)
        sensitive_result = self.client.post(
            f'{self.versions_url(secret_variable)}compare/',
            {'left_version_id': secret_first.pk, 'right_version_id': secret_second.pk}, format='json',
        )
        self.assertEqual(sensitive_result.status_code, 403)
        self.authenticate(self.manager)
        sensitive_result = self.client.post(
            f'{self.versions_url(secret_variable)}compare/',
            {'left_version_id': secret_first.pk, 'right_version_id': secret_second.pk}, format='json',
        )
        self.assertEqual(sensitive_result.status_code, 200)
        self.assertEqual(sensitive_result.json()['different'], True)
        self.assertNotIn('secret-one', sensitive_result.content.decode())
        self.assertNotIn('secret-two', sensitive_result.content.decode())
        self.assertTrue(EnvironmentVariableAuditEvent.objects.filter(action='version_compared').exists())

    def test_restore_creates_a_new_version_and_audit_and_preserves_sensitive_classification(self):
        standard = self.create_variable(value='original')
        original = EnvironmentVariableVersion.objects.get(variable=standard)
        self.update(standard, {'value': 'changed'})
        self.authenticate(self.manager)
        restored = self.client.post(f'{self.versions_url(standard)}{original.pk}/restore/', {}, format='json')
        self.assertEqual(restored.status_code, 200, restored.content)
        standard.refresh_from_db()
        self.assertEqual(standard.value, 'original')
        latest = EnvironmentVariableVersion.objects.filter(variable=standard).order_by('-version_number').first()
        self.assertEqual((latest.action, latest.version_number), ('restored', 3))
        self.assertEqual(EnvironmentVariableAuditEvent.objects.get(action='restored').changes['restored_from']['after'], 1)
        restore_event = EnvironmentVariableAuditEvent.objects.get(action='restored')
        self.assertNotIn('original', str(restore_event.changes))
        self.assertNotIn('changed', str(restore_event.changes))

        sensitive = self.create_variable(key='SECRET_RESTORE', value='protected-original', sensitivity='sensitive')
        sensitive_original = EnvironmentVariableVersion.objects.get(variable=sensitive)
        self.update(sensitive, {'value': 'protected-new'})
        restored_sensitive = self.client.post(
            f'{self.versions_url(sensitive)}{sensitive_original.pk}/restore/', {}, format='json',
        )
        self.assertEqual(restored_sensitive.status_code, 200)
        sensitive.refresh_from_db()
        self.assertEqual(sensitive.sensitivity, 'sensitive')
        self.assertEqual(decrypt_historical_value(
            EnvironmentVariableVersion.objects.filter(variable=sensitive).order_by('-version_number').first(),
        ), 'protected-original')

    def test_member_cannot_restore_and_invalid_or_cross_variable_versions_are_rejected(self):
        variable = self.create_variable(value='allowed')
        version = EnvironmentVariableVersion.objects.get(variable=variable)
        other = self.create_variable(key='OTHER', value='different')
        self.authenticate(self.member)
        denied = self.client.post(f'{self.versions_url(variable)}{version.pk}/restore/', {}, format='json')
        self.assertEqual(denied.status_code, 403)
        self.authenticate(self.owner)
        cross_variable = self.client.post(f'{self.versions_url(other)}{version.pk}/restore/', {}, format='json')
        self.assertEqual(cross_variable.status_code, 404)
        self.assertEqual(EnvironmentVariableVersion.objects.filter(variable=variable).count(), 1)

    def test_import_versions_track_only_actual_changes(self):
        self.authenticate(self.owner)
        preview_url = f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/import/preview/'
        confirm_url = f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/import/confirm/'
        classifications = {'IMPORTED': 'standard'}

        def import_content(content):
            preview = self.client.post(preview_url, {'content': content, 'classifications': classifications}, format='json')
            self.assertEqual(preview.status_code, 200)
            return self.client.post(confirm_url, {
                'content': content, 'classifications': classifications,
                'confirm': True, 'preview_token': preview.json()['preview_token'],
            }, format='json')

        self.assertEqual(import_content('IMPORTED=one').status_code, 200)
        imported = EnvironmentVariable.objects.get(environment=self.environment, key='IMPORTED')
        self.assertEqual(EnvironmentVariableVersion.objects.filter(variable_id_snapshot=imported.pk).count(), 1)
        self.assertEqual(import_content('IMPORTED=one').json(), {'created': 0, 'updated': 0, 'unchanged': 1})
        self.assertEqual(EnvironmentVariableVersion.objects.filter(variable_id_snapshot=imported.pk).count(), 1)
        self.assertEqual(import_content('IMPORTED=two').status_code, 200)
        self.assertEqual(EnvironmentVariableVersion.objects.filter(variable_id_snapshot=imported.pk).count(), 2)

    def test_delete_preserves_encrypted_history_and_nulls_variable_reference(self):
        secret = 'deleted-secret-snapshot'
        variable = self.create_variable(key='DELETED', value=secret, sensitivity='sensitive')
        variable_id = variable.pk
        self.authenticate(self.owner)
        response = self.client.delete(f'{self.variables_url()}{variable_id}/')
        self.assertEqual(response.status_code, 204)
        version = EnvironmentVariableVersion.objects.get(variable_id_snapshot=variable_id, action='deleted')
        self.assertIsNone(version.variable_id)
        self.assertEqual(version.action, 'deleted')
        self.assertNotIn(secret, version.encrypted_value)
        self.assertEqual(decrypt_historical_value(version), secret)
        history_url = f'{self.variables_url()}{variable_id}/versions/'
        self.assertEqual(self.client.get(history_url).status_code, 404)
        self.assertEqual(self.client.get(f'{history_url}{version.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'{history_url}{version.pk}/value/').status_code, 404)
        self.assertEqual(self.client.post(f'{history_url}{version.pk}/restore/', {}, format='json').status_code, 404)
        self.assertEqual(
            self.client.post(
                f'{history_url}compare/',
                {'left_version_id': version.pk, 'right_version_id': version.pk}, format='json',
            ).status_code,
            404,
        )
        outsider = APIClient()
        outsider.force_authenticate(self.outsider)
        self.assertNotEqual(outsider.get(history_url).status_code, 200)
        self.assertEqual(
            EnvironmentVariableVersion.objects.filter(variable_id_snapshot=variable_id).count(), 2,
        )

    def test_history_encryption_failure_rolls_back_standard_variable_creation(self):
        self.authenticate(self.owner)
        with self.settings(ENVSHARE_ENCRYPTION_KEY=''):
            response = self.client.post(
                self.variables_url(), {'key': 'ROLLBACK', 'value': 'not-stored', 'sensitivity': 'standard'}, format='json',
            )
        self.assertEqual(response.status_code, 503)
        self.assertFalse(EnvironmentVariable.objects.filter(environment=self.environment, key='ROLLBACK').exists())
        self.assertFalse(EnvironmentVariableVersion.objects.exists())

    def test_restore_audit_failure_rolls_back_variable_and_version(self):
        variable = self.create_variable(value='before')
        version = EnvironmentVariableVersion.objects.get(variable=variable)
        self.update(variable, {'value': 'after'})
        before_count = EnvironmentVariableVersion.objects.filter(variable=variable).count()
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(self.owner)
        with patch('projects.version_views.record_variable_audit', side_effect=RuntimeError('private audit failure')):
            response = client.post(f'{self.versions_url(variable)}{version.pk}/restore/', {}, format='json')
        self.assertEqual(response.status_code, 500)
        variable.refresh_from_db()
        self.assertEqual(variable.value, 'after')
        self.assertEqual(EnvironmentVariableVersion.objects.filter(variable=variable).count(), before_count)

    def test_cross_project_versions_are_not_visible(self):
        variable = self.create_variable()
        version = EnvironmentVariableVersion.objects.get(variable=variable)
        other_project = Project.objects.create(name='Other version project', creator=self.outsider)
        other_environment = other_project.environments.get(name=Environment.Name.DEVELOPMENT)
        self.authenticate(self.owner)
        response = self.client.get(
            f'/api/projects/{other_project.pk}/environments/{other_environment.pk}/variables/{variable.pk}/versions/{version.pk}/',
        )
        self.assertEqual(response.status_code, 404)

    def test_sensitive_access_audit_failure_withholds_historical_plaintext(self):
        secret = 'audit-fail-closed-history'
        variable = self.create_variable(key='AUDIT_FAIL', value=secret, sensitivity='sensitive')
        version = EnvironmentVariableVersion.objects.get(variable=variable)
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(self.manager)
        with patch('projects.version_views.record_variable_audit', side_effect=RuntimeError('private failure')):
            response = client.get(f'{self.versions_url(variable)}{version.pk}/value/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(secret, response.content.decode())

    def test_version_number_uniqueness_is_enforced(self):
        variable = self.create_variable()
        version = EnvironmentVariableVersion.objects.get(variable=variable)
        duplicate = EnvironmentVariableVersion(
            project=version.project,
            environment=version.environment,
            environment_id_snapshot=version.environment_id_snapshot,
            variable=variable,
            variable_id_snapshot=variable.pk,
            variable_key=version.variable_key,
            version_number=version.version_number,
            encrypted_value=version.encrypted_value,
            sensitivity=version.sensitivity,
            action=version.action,
            actor=version.actor,
            actor_username=version.actor_username,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()
