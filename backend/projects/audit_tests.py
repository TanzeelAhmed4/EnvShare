import base64
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .encryption import encrypt_value
from .models import (
    Environment, EnvironmentVariable, EnvironmentVariableAuditEvent,
    Project, ProjectAccessAuditEvent, ProjectMembership,
)


TEST_KEY = base64.urlsafe_b64encode(b'A' * 32).decode('ascii')
User = get_user_model()


@override_settings(
    ENVSHARE_ENCRYPTION_KEY=TEST_KEY,
    ENVSHARE_HISTORY_ENCRYPTION_KEY=base64.urlsafe_b64encode(b'B' * 32).decode('ascii'),
)
class EnvironmentVariableAuditTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='audit-owner', password='Strong-Password-882!')
        self.member = User.objects.create_user(username='audit-member', password='Strong-Password-882!')
        self.outsider = User.objects.create_user(username='audit-outsider', password='Strong-Password-882!')
        self.project = Project.objects.create(name='Audit project', creator=self.owner)
        ProjectMembership.objects.create(project=self.project, user=self.member, added_by=self.owner, role=ProjectMembership.Role.MANAGER)
        self.environment = self.project.environments.get(name=Environment.Name.DEVELOPMENT)
        self.client = APIClient()

    def variables_url(self):
        return f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/variables/'

    def audit_url(self):
        return f'/api/projects/{self.project.pk}/audit/'

    def reveal_url(self, variable):
        return f'{self.variables_url()}{variable.pk}/reveal/'

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

    def test_successful_sensitive_reveal_records_context_without_plaintext(self):
        secret = 'reveal-audit-secret-marker-73'
        variable = self.create_variable('PRIVATE_TOKEN', secret, 'sensitive')
        self.client.force_authenticate(user=self.member)

        response = self.client.post(self.reveal_url(variable), {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'key': 'PRIVATE_TOKEN', 'value': secret})
        events = EnvironmentVariableAuditEvent.objects.filter(
            action=EnvironmentVariableAuditEvent.Action.REVEALED,
        )
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.actor, self.member)
        self.assertEqual(event.actor_username, 'audit-member')
        self.assertEqual(event.project, self.project)
        self.assertEqual(event.project_name, self.project.name)
        self.assertEqual(event.environment, self.environment)
        self.assertEqual(event.environment_name, self.environment.name)
        self.assertEqual(event.variable_id, variable.pk)
        self.assertEqual(event.variable_key, 'PRIVATE_TOKEN')
        self.assertTrue(event.created_at)
        self.assertEqual(event.changes, {})

        audit_data = json.dumps(event.__dict__, default=str)
        timeline = self.client.get(self.audit_url())
        self.assertEqual(timeline.status_code, 200)
        self.assertIn('revealed', timeline.content.decode())
        self.assertNotIn(secret, audit_data)
        self.assertNotIn(secret, timeline.content.decode())

    def test_each_successful_reveal_creates_a_separate_event(self):
        variable = self.create_variable('REPEATED_TOKEN', 'repeat-secret', 'sensitive')
        self.client.force_authenticate(user=self.member)

        first = self.client.post(self.reveal_url(variable), {}, format='json')
        second = self.client.post(self.reveal_url(variable), {}, format='json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        events = list(EnvironmentVariableAuditEvent.objects.filter(
            action=EnvironmentVariableAuditEvent.Action.REVEALED,
            variable_id=variable.pk,
        ))
        self.assertEqual(len(events), 2)
        self.assertNotEqual(events[0].pk, events[1].pk)

    def test_unauthorized_and_failed_reveals_do_not_create_reveal_events(self):
        sensitive = self.create_variable('PRIVATE_TOKEN', 'private-secret', 'sensitive')
        standard = self.create_variable('PUBLIC_VALUE', 'ordinary-value', 'standard')

        self.client.force_authenticate(user=self.outsider)
        unauthorized = self.client.post(self.reveal_url(sensitive), {}, format='json')

        self.client.force_authenticate(user=self.member)
        missing = self.client.post(
            f'{self.variables_url()}999999/reveal/', {}, format='json',
        )
        standard_response = self.client.post(self.reveal_url(standard), {}, format='json')
        EnvironmentVariable.objects.filter(pk=sensitive.pk).update(value='aesgcm:v1:broken')
        failed_decryption = self.client.post(self.reveal_url(sensitive), {}, format='json')

        self.assertEqual(unauthorized.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(standard_response.status_code, 400)
        self.assertEqual(failed_decryption.status_code, 503)
        self.assertNotIn('private-secret', failed_decryption.content.decode())
        self.assertFalse(EnvironmentVariableAuditEvent.objects.filter(
            action=EnvironmentVariableAuditEvent.Action.REVEALED,
        ).exists())

    def test_audit_recording_failure_does_not_return_decrypted_secret(self):
        secret = 'never-return-when-audit-fails-81'
        variable = self.create_variable('FAIL_CLOSED_TOKEN', secret, 'sensitive')
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=self.member)

        with patch(
            'projects.environment_views.record_variable_audit',
            side_effect=RuntimeError('private audit failure detail'),
        ):
            response = client.post(self.reveal_url(variable), {}, format='json')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'detail': 'The variable reveal could not be audited.'})
        self.assertNotIn(secret, response.content.decode())
        self.assertNotIn('private audit failure detail', response.content.decode())
        self.assertFalse(EnvironmentVariableAuditEvent.objects.filter(
            action=EnvironmentVariableAuditEvent.Action.REVEALED,
        ).exists())

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
        self.assertEqual(member_response.json()['results'][0]['actor'], 'audit-owner')
        self.assertEqual(member_response.json()['results'][0]['environment_label'], 'Development')

        self.client.force_authenticate(user=self.outsider)
        outsider_response = self.client.get(self.audit_url())
        self.assertEqual(outsider_response.status_code, 404)

    def test_audit_filters_pagination_and_invalid_filters(self):
        self.create_variable('FILTER_ONE', 'one')
        self.create_variable('FILTER_TWO', 'two')
        self.client.force_authenticate(user=self.member)
        filtered = self.client.get(
            self.audit_url(), {'search': 'FILTER_ONE', 'environment': self.environment.pk, 'actor': self.owner.username},
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()['count'], 1)
        self.assertEqual(filtered.json()['results'][0]['variable_key'], 'FILTER_ONE')
        self.assertEqual(filtered.json()['page'], 1)
        self.assertEqual(self.client.get(self.audit_url(), {'action': 'not-an-action'}).status_code, 400)
        self.assertEqual(self.client.get(self.audit_url(), {'date_from': 'yesterday'}).status_code, 400)
        self.assertEqual(self.client.get(self.audit_url(), {'page_size': 101}).status_code, 400)

        events = [
            EnvironmentVariableAuditEvent.objects.create(
                project=self.project, environment=self.environment, variable_id=900 + index,
                variable_key=f'PAGE_{index}', action='updated', actor=self.owner,
                actor_username=self.owner.username, project_name=self.project.name,
                environment_name=self.environment.name, changes={},
            )
            for index in range(3)
        ]
        first_page = self.client.get(self.audit_url(), {'page_size': 2, 'page': 1, 'action': 'updated'})
        second_page = self.client.get(self.audit_url(), {'page_size': 2, 'page': 2, 'action': 'updated'})
        self.assertEqual((first_page.json()['count'], len(first_page.json()['results'])), (3, 2))
        self.assertEqual((second_page.json()['page'], len(second_page.json()['results'])), (2, 1))
        self.assertNotEqual(first_page.json()['results'][0]['id'], first_page.json()['results'][1]['id'])

        ProjectAccessAuditEvent.objects.create(
            project=self.project, actor=self.owner, actor_username=self.owner.username,
            action=ProjectAccessAuditEvent.Action.MEMBERSHIP_ADDED, target_username='filter-target',
        )
        access = self.client.get(
            f'/api/projects/{self.project.pk}/access-audit/',
            {'action': 'membership_added', 'actor': self.owner.username},
        )
        self.assertEqual(access.status_code, 200)
        self.assertEqual(access.json()['count'], 1)

        EnvironmentVariableAuditEvent.objects.create(
            project=self.project, environment=self.environment, variable_id=999,
            variable_key='IMPORTED_KEY', action='created', actor=self.owner,
            actor_username=self.owner.username, project_name=self.project.name,
            environment_name=self.environment.name,
            changes={'source': {'before': None, 'after': 'bulk_import'}},
        )
        imported = self.client.get(self.audit_url(), {'action': 'bulk_imported'})
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()['count'], 1)

    def test_audit_history_is_read_only_and_project_deletion_preserves_audit_and_versions(self):
        variable = self.create_variable('PRESERVED', 'value')
        project_id = self.project.pk
        event = EnvironmentVariableAuditEvent.objects.get(variable_key='PRESERVED')
        version = variable.versions.get()
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.post(self.audit_url(), {}, format='json').status_code, 405)
        self.assertEqual(self.client.patch(self.audit_url(), {}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(self.audit_url()).status_code, 405)
        access_event = ProjectAccessAuditEvent.objects.create(
            project=self.project, actor=self.owner, actor_username=self.owner.username,
            action=ProjectAccessAuditEvent.Action.PROJECT_CREATED,
        )
        deleted = self.client.delete(f'/api/projects/{project_id}/delete/')
        self.assertEqual(deleted.status_code, 204)
        event.refresh_from_db()
        version.refresh_from_db()
        access_event.refresh_from_db()
        self.assertIsNone(event.project_id)
        self.assertEqual(event.project_id_snapshot, project_id)
        self.assertIsNone(version.project_id)
        self.assertEqual(version.project_id_snapshot, project_id)
        self.assertIsNone(access_event.project_id)
        self.assertEqual(access_event.project_id_snapshot, project_id)

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

    def test_import_audit_failure_rolls_back_variables_versions_and_audits(self):
        self.client.force_authenticate(user=self.owner)
        confirm_url = f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/import/confirm/'
        preview = self.client.post(
            confirm_url.replace('/confirm/', '/preview/'),
            {'content': 'ROLLBACK_IMPORT=value', 'classifications': {'ROLLBACK_IMPORT': 'standard'}},
            format='json',
        )
        self.assertEqual(preview.status_code, 200)
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=self.owner)
        with patch('projects.environment_views.record_variable_audit', side_effect=RuntimeError('audit failed')):
            response = client.post(confirm_url, {
                'content': 'ROLLBACK_IMPORT=value', 'classifications': {'ROLLBACK_IMPORT': 'standard'},
                'confirm': True, 'preview_token': preview.json()['preview_token'],
            }, format='json')
        self.assertEqual(response.status_code, 500)
        self.assertFalse(EnvironmentVariable.objects.filter(environment=self.environment, key='ROLLBACK_IMPORT').exists())
        from .models import EnvironmentVariableVersion
        self.assertFalse(EnvironmentVariableVersion.objects.filter(variable_key='ROLLBACK_IMPORT').exists())

