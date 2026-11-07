import base64
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .encryption import encrypt_value
from .models import Environment, EnvironmentVariable, EnvironmentVariableAuditEvent, Project, ProjectMembership


TEST_KEY = base64.urlsafe_b64encode(b'A' * 32).decode('ascii')
User = get_user_model()


@override_settings(ENVSHARE_ENCRYPTION_KEY=TEST_KEY)
class EnvironmentVariableAuditTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='audit-owner', password='Strong-Password-882!')
        self.member = User.objects.create_user(username='audit-member', password='Strong-Password-882!')
        self.outsider = User.objects.create_user(username='audit-outsider', password='Strong-Password-882!')
        self.project = Project.objects.create(name='Audit project', creator=self.owner)
        ProjectMembership.objects.create(project=self.project, user=self.member, added_by=self.owner)
        self.environment = self.project.environments.get(name=Environment.Name.DEVELOPMENT)
        self.client = APIClient()

    def variables_url(self):
        return f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/variables/'

    def audit_url(self):
        return f'/api/projects/{self.project.pk}/audit/'

    def create_variable(self, key='TOKEN_NAME', value='plain-before', sensitivity='standard', user=None):
        self.client.force_authenticate(user=user or self.owner)
        response = self.client.post(
            self.variables_url(),
            {'key': key, 'value': value, 'sensitivity': sensitivity},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        return EnvironmentVariable.objects.get(pk=response.json()['id'])

    def test_creation_records_project_environment_key_actor_and_timestamp(self):
        self.create_variable()

        event = EnvironmentVariableAuditEvent.objects.get()
        self.assertEqual(event.action, EnvironmentVariableAuditEvent.Action.CREATED)
        self.assertEqual(event.project, self.project)
        self.assertEqual(event.environment, self.environment)
        self.assertEqual(event.variable_key, 'TOKEN_NAME')
        self.assertEqual(event.actor, self.owner)
        self.assertEqual(event.actor_username, 'audit-owner')
        self.assertIsNotNone(event.created_at)
        self.assertEqual(event.changes['value'], {'before': None, 'after': 'plain-before'})

    def test_update_records_actor_and_safe_before_after_details(self):
        variable = self.create_variable()
        self.client.force_authenticate(user=self.member)

        response = self.client.patch(
            f'{self.variables_url()}{variable.pk}/',
            {'key': 'RENAMED_TOKEN', 'value': 'plain-after'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        event = EnvironmentVariableAuditEvent.objects.get(action='updated')
        self.assertEqual(event.actor, self.member)
        self.assertEqual(event.variable_key, 'RENAMED_TOKEN')
        self.assertEqual(event.changes['key'], {'before': 'TOKEN_NAME', 'after': 'RENAMED_TOKEN'})
        self.assertEqual(event.changes['value'], {'before': 'plain-before', 'after': 'plain-after'})

    def test_delete_records_actor_and_retains_event_after_variable_removal(self):
        variable = self.create_variable()
        self.client.force_authenticate(user=self.member)

        response = self.client.delete(f'{self.variables_url()}{variable.pk}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(EnvironmentVariable.objects.filter(pk=variable.pk).exists())
        event = EnvironmentVariableAuditEvent.objects.get(action='deleted')
        self.assertEqual(event.actor, self.member)
        self.assertEqual(event.variable_key, 'TOKEN_NAME')
        self.assertEqual(event.changes['value'], {'before': 'plain-before', 'after': None})

    def test_sensitive_plaintext_never_enters_audit_json_or_timeline_response(self):
        secret_one = 'audit-sensitive-original-92'
        secret_two = 'audit-sensitive-updated-47'
        variable = self.create_variable('PRIVATE_TOKEN', secret_one, 'sensitive')
        self.client.force_authenticate(user=self.member)
        self.client.patch(
            f'{self.variables_url()}{variable.pk}/',
            {'value': secret_two},
            format='json',
        )
        self.client.delete(f'{self.variables_url()}{variable.pk}/')

        all_changes = json.dumps(list(EnvironmentVariableAuditEvent.objects.values_list('changes', flat=True)))
        timeline = self.client.get(self.audit_url())
        self.assertEqual(timeline.status_code, 200)
        self.assertNotIn(secret_one, all_changes)
        self.assertNotIn(secret_two, all_changes)
        self.assertNotIn(secret_one, timeline.content.decode())
        self.assertNotIn(secret_two, timeline.content.decode())
        self.assertEqual(EnvironmentVariableAuditEvent.objects.count(), 3)
        for event in EnvironmentVariableAuditEvent.objects.all():
            self.assertIn('[REDACTED]', json.dumps(event.changes))

    def test_import_creation_and_update_generate_events_with_safe_values(self):
        secret = 'import-audit-secret-value'
        existing = EnvironmentVariable.objects.create(
            environment=self.environment,
            key='PRIVATE_IMPORT',
            value=encrypt_value('old-private-value', self.environment, 'PRIVATE_IMPORT'),
            sensitivity='sensitive',
        )
        self.client.force_authenticate(user=self.member)
        url = f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/import/confirm/'
        preview = self.client.post(
            url.replace('/confirm/', '/preview/'),
            {
                'content': f'PRIVATE_IMPORT={secret}\nNEW_PRIVATE={secret}',
                'classifications': {'NEW_PRIVATE': 'sensitive'},
            },
            format='json',
        )
        self.assertEqual(preview.status_code, 200)
        response = self.client.post(
            url,
            {
                'content': f'PRIVATE_IMPORT={secret}\nNEW_PRIVATE={secret}',
                'classifications': {'NEW_PRIVATE': 'sensitive'},
                'confirm': True,
                'preview_token': preview.json()['preview_token'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        events = list(EnvironmentVariableAuditEvent.objects.order_by('variable_key'))
        self.assertEqual(len(events), 2)
        self.assertEqual({event.action for event in events}, {'created', 'updated'})
        self.assertTrue(all(event.actor == self.member for event in events))
        self.assertEqual(
            EnvironmentVariable.objects.get(pk=existing.pk).sensitivity,
            EnvironmentVariable.Sensitivity.SENSITIVE,
        )
        audit_json = json.dumps([event.changes for event in events])
        response_text = response.content.decode()
        self.assertNotIn(secret, audit_json)
        self.assertNotIn(secret, response_text)
        self.assertTrue(all('[REDACTED]' in json.dumps(event.changes) for event in events))

    def test_members_can_view_project_history_but_non_members_cannot(self):
        self.create_variable()
        self.client.force_authenticate(user=self.member)
        member_response = self.client.get(self.audit_url())
        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(member_response.json()[0]['actor'], 'audit-owner')
        self.assertEqual(member_response.json()[0]['environment_label'], 'Development')

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get(self.audit_url())
        self.assertEqual(outsider_response.status_code, 404)

    def test_audit_write_failure_rolls_back_variable_creation(self):
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=self.owner)
        with patch('projects.environment_views.record_variable_audit', side_effect=RuntimeError('audit failure')):
            response = client.post(
                self.variables_url(),
                {'key': 'ROLLBACK_ME', 'value': 'plain-value', 'sensitivity': 'standard'},
                format='json',
            )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(EnvironmentVariable.objects.filter(key='ROLLBACK_ME').exists())
        self.assertFalse(EnvironmentVariableAuditEvent.objects.exists())

