from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    Environment,
    EnvironmentVariable,
    EnvironmentVariableVersion,
    Project,
    ProjectAccessAuditEvent,
    ProjectInvitation,
    ProjectMembership,
)
from .invitation_views import token_digest
from django.utils import timezone
from datetime import timedelta


User = get_user_model()
POSTGRES_AVAILABLE = connection.vendor == 'postgresql'


@skipUnless(POSTGRES_AVAILABLE, 'requires a real PostgreSQL test database')
@override_settings(ENVSHARE_ENCRYPTION_KEY='V' * 43 + '=')
class PostgreSQLConcurrencyIntegrationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(username='pg-owner', email='pg-owner@example.test')
        self.invited = User.objects.create_user(username='pg-invited', email='pg-invited@example.test')
        self.project = Project.objects.create(name='PostgreSQL integration', creator=self.owner)
        self.environment = self.project.environments.get(name=Environment.Name.DEVELOPMENT)

    def test_concurrent_updates_serialize_variable_history(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        url = f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/variables/'
        created = client.post(url, {'key': 'PG_VALUE', 'value': 'initial', 'sensitivity': 'standard'}, format='json')
        self.assertEqual(created.status_code, 201)
        variable_id = created.json()['id']
        barrier = Barrier(2)

        def update(value):
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.owner.pk)
                local = APIClient()
                local.force_authenticate(actor)
                barrier.wait(timeout=10)
                return local.patch(f'{url}{variable_id}/', {'value': value}, format='json').status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(update, ('concurrent-left', 'concurrent-right')))
        self.assertEqual(statuses, [200, 200])
        self.assertEqual(list(EnvironmentVariableVersion.objects.filter(
            variable_id_snapshot=variable_id,
        ).order_by('version_number').values_list('version_number', flat=True)), [1, 2, 3])

    def test_concurrent_invitation_acceptance_consumes_one_use_and_audits_once(self):
        token = 'postgres-concurrent-invitation-token'
        invitation = ProjectInvitation.objects.create(
            project=self.project, invited_email=self.invited.email, token_hash=token_digest(token),
            role='member', expires_at=timezone.now() + timedelta(hours=1), max_uses=1,
        )
        barrier = Barrier(2)

        def accept():
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.invited.pk)
                local = APIClient()
                local.force_authenticate(actor)
                barrier.wait(timeout=10)
                return local.post('/api/projects/invitations/accept/', {'token': token}, format='json').status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _index: accept(), range(2)))
        invitation.refresh_from_db()
        self.assertEqual(statuses.count(200), 1)
        self.assertEqual(invitation.use_count, 1)
        self.assertEqual(self.project.memberships.filter(user=self.invited).count(), 1)
        self.assertEqual(ProjectAccessAuditEvent.objects.filter(
            project=self.project, action=ProjectAccessAuditEvent.Action.INVITATION_ACCEPTED,
        ).count(), 1)

    def test_concurrent_import_confirmation_commits_one_consistent_history(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        root = f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/import/'
        content = 'PG_IMPORTED=once'
        classifications = {'PG_IMPORTED': 'standard'}
        preview = client.post(f'{root}preview/', {
            'content': content, 'classifications': classifications,
        }, format='json')
        self.assertEqual(preview.status_code, 200, preview.content)
        token = preview.json()['preview_token']
        barrier = Barrier(2)

        def confirm():
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.owner.pk)
                local = APIClient()
                local.force_authenticate(actor)
                barrier.wait(timeout=10)
                return local.post(f'{root}confirm/', {
                    'content': content, 'classifications': classifications,
                    'confirm': True, 'preview_token': token,
                }, format='json').status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _index: confirm(), range(2)))
        self.assertEqual(statuses.count(200), 1)
        variable = EnvironmentVariable.objects.get(environment=self.environment, key='PG_IMPORTED')
        self.assertEqual(list(EnvironmentVariableVersion.objects.filter(
            variable_id_snapshot=variable.pk,
        ).values_list('version_number', flat=True)), [1])

    def test_concurrent_restorations_append_versions_without_overwriting_history(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        root = f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/variables/'
        created = client.post(root, {
            'key': 'PG_RESTORE', 'value': 'original', 'sensitivity': 'standard',
        }, format='json')
        self.assertEqual(created.status_code, 201)
        variable_id = created.json()['id']
        first = EnvironmentVariableVersion.objects.get(variable_id_snapshot=variable_id, version_number=1)
        changed = client.patch(f'{root}{variable_id}/', {'value': 'changed'}, format='json')
        self.assertEqual(changed.status_code, 200)
        barrier = Barrier(2)

        def restore():
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.owner.pk)
                local = APIClient()
                local.force_authenticate(actor)
                barrier.wait(timeout=10)
                return local.post(f'{root}{variable_id}/versions/{first.pk}/restore/', {}, format='json').status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _index: restore(), range(2)))
        self.assertEqual(statuses, [200, 200])
        self.assertEqual(list(EnvironmentVariableVersion.objects.filter(
            variable_id_snapshot=variable_id,
        ).order_by('version_number').values_list('version_number', flat=True)), [1, 2, 3, 4])
        self.assertEqual(EnvironmentVariableVersion.objects.filter(
            variable_id_snapshot=variable_id, action='restored',
        ).count(), 2)

    def test_concurrent_membership_role_changes_keep_before_after_audit_consistent(self):
        member = User.objects.create_user(username='pg-role-target', email='pg-role-target@example.test')
        ProjectMembership.objects.create(
            project=self.project, user=member, added_by=self.owner, role=ProjectMembership.Role.MEMBER,
        )
        barrier = Barrier(2)

        def change(role):
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.owner.pk)
                local = APIClient()
                local.force_authenticate(actor)
                barrier.wait(timeout=10)
                return local.patch(
                    f'/api/projects/{self.project.pk}/members/{member.pk}/', {'role': role}, format='json',
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(change, ('manager', 'admin')))
        self.assertEqual(statuses, [200, 200])
        events = list(ProjectAccessAuditEvent.objects.filter(
            project=self.project, action=ProjectAccessAuditEvent.Action.ROLE_CHANGED,
            target_username=member.username,
        ).order_by('pk').values_list('role_before', 'role_after'))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0][0], ProjectMembership.Role.MEMBER)
        self.assertEqual(events[0][1], events[1][0])
        self.assertIn(events[1][1], (ProjectMembership.Role.ADMIN, ProjectMembership.Role.MANAGER))
