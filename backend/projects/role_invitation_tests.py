import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError, connection
from django.test import TestCase, override_settings
from django.test import TransactionTestCase
from django.db import close_old_connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.test import APIClient

from .encryption import encrypt_value
from .invitation_views import claim_invitation_use, token_digest
from .models import Environment, EnvironmentVariable, Project, ProjectAccessAuditEvent, ProjectInvitation, ProjectMembership

User = get_user_model()
TEST_KEY = base64.urlsafe_b64encode(b'R' * 32).decode('ascii')


@override_settings(ENVSHARE_ENCRYPTION_KEY=TEST_KEY)
class ProjectRoleAndInvitationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='role-owner', email='owner@example.test', password='Strong-Password-882!')
        self.admin = User.objects.create_user(username='role-admin', email='admin@example.test', password='Strong-Password-882!')
        self.manager = User.objects.create_user(username='role-manager', email='manager@example.test', password='Strong-Password-882!')
        self.member = User.objects.create_user(username='role-member', email='member@example.test', password='Strong-Password-882!')
        self.outsider = User.objects.create_user(username='role-outsider', email='outsider@example.test', password='Strong-Password-882!')
        self.project = Project.objects.create(name='Role project', creator=self.owner)
        ProjectMembership.objects.create(project=self.project, user=self.admin, added_by=self.owner, role='admin')
        ProjectMembership.objects.create(project=self.project, user=self.manager, added_by=self.owner, role='manager')
        ProjectMembership.objects.create(project=self.project, user=self.member, added_by=self.owner, role='member')
        self.environment = self.project.environments.get(name=Environment.Name.DEVELOPMENT)
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def variable_url(self):
        return f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/variables/'

    def test_role_matrix_enforced_for_variable_actions(self):
        for user in (self.owner, self.admin, self.manager):
            self.authenticate(user)
            self.assertEqual(self.client.post(self.variable_url(), {'key': f'VALUE_{user.pk}', 'value': 'v', 'sensitivity': 'standard'}, format='json').status_code, 201)
        self.authenticate(self.member)
        self.assertEqual(self.client.get(self.variable_url()).status_code, 200)
        self.assertEqual(self.client.get(f'/api/projects/{self.project.pk}/audit/').status_code, 200)
        self.assertEqual(self.client.post(self.variable_url(), {'key': 'READ_ONLY', 'value': 'v', 'sensitivity': 'standard'}, format='json').status_code, 403)
        variable = EnvironmentVariable.objects.create(environment=self.environment, key='NOT_EDITABLE', value='before')
        self.assertEqual(self.client.patch(f'{self.variable_url()}{variable.pk}/', {'value': 'after'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'{self.variable_url()}{variable.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/import/confirm/', {'content': 'X=1', 'confirm': True, 'preview_token': 'invalid'}, format='json').status_code, 403)
        variable = EnvironmentVariable.objects.create(environment=self.environment, key='SEALED', value=encrypt_value('safe', self.environment, 'SEALED'), sensitivity='sensitive')
        self.assertEqual(self.client.post(f'{self.variable_url()}{variable.pk}/reveal/', {}, format='json').status_code, 403)
        self.assertEqual(self.client.post(f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/import/preview/', {'content': 'X=1'}, format='json').status_code, 403)
        self.authenticate(self.outsider)
        self.assertEqual(self.client.get(self.variable_url()).status_code, 404)

    def test_admin_cannot_assign_admin_or_promote_self_but_owner_can_assign_admin(self):
        url = f'/api/projects/{self.project.pk}/members/'
        self.authenticate(self.admin)
        self.assertEqual(self.client.post(url, {'username': self.outsider.username, 'role': 'admin'}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(f'{url}{self.admin.pk}/', {'role': 'manager'}, format='json').status_code, 403)
        self.authenticate(self.owner)
        promoted = self.client.post(url, {'username': self.outsider.username, 'role': 'admin'}, format='json')
        self.assertEqual(promoted.status_code, 201)
        self.assertEqual(promoted.json()['role'], 'admin')
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.owner).exists())

    def test_admin_cannot_demote_or_remove_another_admin_or_modify_the_owner(self):
        other_admin = User.objects.create_user(username='other-admin', email='other-admin@example.test')
        another_admin = User.objects.create_user(username='another-admin', email='another-admin@example.test')
        ProjectMembership.objects.create(project=self.project, user=other_admin, added_by=self.owner, role='admin')
        ProjectMembership.objects.create(project=self.project, user=another_admin, added_by=self.owner, role='admin')
        members = f'/api/projects/{self.project.pk}/members/'
        self.authenticate(self.admin)
        demoted = self.client.patch(f'{members}{other_admin.pk}/', {'role': 'manager'}, format='json')
        removed = self.client.delete(f'{members}{another_admin.pk}/')
        self.assertEqual(demoted.status_code, 403)
        self.assertEqual(removed.status_code, 403)
        self.assertEqual(ProjectMembership.objects.get(project=self.project, user=other_admin).role, 'admin')
        self.assertTrue(ProjectMembership.objects.filter(project=self.project, user=another_admin, role='admin').exists())
        self.assertEqual(self.client.patch(f'{members}{self.owner.pk}/', {'role': 'member'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'{members}{self.owner.pk}/').status_code, 403)
        self.assertEqual(self.client.post(members, {'username': self.owner.username, 'role': 'member'}, format='json').status_code, 400)

    def test_owner_can_demote_and_remove_an_admin(self):
        demote_admin = User.objects.create_user(username='demote-admin', email='demote-admin@example.test')
        remove_admin = User.objects.create_user(username='remove-admin', email='remove-admin@example.test')
        ProjectMembership.objects.create(project=self.project, user=demote_admin, added_by=self.owner, role='admin')
        ProjectMembership.objects.create(project=self.project, user=remove_admin, added_by=self.owner, role='admin')
        members = f'/api/projects/{self.project.pk}/members/'
        self.authenticate(self.owner)
        demoted = self.client.patch(f'{members}{demote_admin.pk}/', {'role': 'manager'}, format='json')
        removed = self.client.delete(f'{members}{remove_admin.pk}/')
        self.assertEqual(demoted.status_code, 200)
        self.assertEqual(ProjectMembership.objects.get(project=self.project, user=demote_admin).role, 'manager')
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=remove_admin).exists())

    def test_admin_can_manage_managers_and_members(self):
        members = f'/api/projects/{self.project.pk}/members/'
        self.authenticate(self.admin)
        manager_to_member = self.client.patch(f'{members}{self.manager.pk}/', {'role': 'member'}, format='json')
        member_to_manager = self.client.patch(f'{members}{self.member.pk}/', {'role': 'manager'}, format='json')
        self.assertEqual(manager_to_member.status_code, 200)
        self.assertEqual(member_to_manager.status_code, 200)
        self.assertEqual(ProjectMembership.objects.get(project=self.project, user=self.manager).role, 'member')
        self.assertEqual(ProjectMembership.objects.get(project=self.project, user=self.member).role, 'manager')
        self.assertEqual(self.client.delete(f'{members}{self.manager.pk}/').status_code, 204)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.manager).exists())

    def test_manager_and_member_cannot_manage_members_and_only_owner_deletes_project(self):
        members = f'/api/projects/{self.project.pk}/members/'
        for user in (self.manager, self.member):
            self.authenticate(user)
            self.assertEqual(self.client.get(members).status_code, 403)
            self.assertEqual(self.client.delete(f'{members}{self.member.pk}/').status_code, 403)
            self.assertEqual(self.client.patch(f'{members}{self.manager.pk}/', {'role': 'member'}, format='json').status_code, 403)
            self.assertEqual(ProjectMembership.objects.get(project=self.project, user=self.manager).role, 'manager')
            self.assertEqual(ProjectMembership.objects.get(project=self.project, user=self.member).role, 'member')
            self.assertEqual(self.client.delete(f'/api/projects/{self.project.pk}/delete/').status_code, 403)
        self.authenticate(self.admin)
        self.assertEqual(self.client.delete(f'/api/projects/{self.project.pk}/delete/').status_code, 403)
        self.authenticate(self.owner)
        self.assertEqual(self.client.delete(f'/api/projects/{self.project.pk}/delete/').status_code, 204)

    def create_invitation(self, *, user=None, email='invite@example.test', role='member', **extra):
        self.authenticate(user or self.owner)
        return self.client.post(f'/api/projects/{self.project.pk}/invitations/', {
            'email': email, 'role': role, **extra,
        }, format='json')

    def test_invitation_stores_only_token_hash_and_audits_safe_metadata(self):
        response = self.create_invitation(email=' Invite@Example.Test ', role='manager')
        self.assertEqual(response.status_code, 201)
        token = response.json()['token']
        invitation = ProjectInvitation.objects.get(pk=response.json()['id'])
        self.assertEqual(response.json()['token'], token)
        self.assertEqual(invitation.invited_email, 'invite@example.test')
        self.assertNotEqual(invitation.token_hash, token)
        self.assertEqual(len(invitation.token_hash), 64)
        event = ProjectAccessAuditEvent.objects.get(action='invitation_created')
        self.assertNotIn(token, str(event.__dict__))
        listing = self.client.get(f'/api/projects/{self.project.pk}/invitations/')
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn(token, listing.content.decode())
        access_history = self.client.get(f'/api/projects/{self.project.pk}/access-audit/')
        self.assertEqual(access_history.status_code, 200)
        self.assertNotIn(token, access_history.content.decode())
        inspected = self.client.post('/api/projects/invitations/inspect/', {'token': token}, format='json')
        self.assertEqual(inspected.status_code, 200)
        self.assertNotIn(token, inspected.content.decode())

    def test_invitation_authorization_and_assigned_role_limits(self):
        self.assertEqual(self.create_invitation(user=self.manager).status_code, 403)
        self.assertEqual(self.create_invitation(user=self.admin, role='admin').status_code, 403)
        self.assertEqual(self.create_invitation(user=self.owner, email='not-an-email').status_code, 400)
        self.assertEqual(self.create_invitation(user=self.admin, role='member').status_code, 201)
        self.assertEqual(self.create_invitation(user=self.owner, email='multi@example.test', max_uses=2).status_code, 400)

    def test_acceptance_requires_matching_email_and_rejects_invalid_expired_revoked_and_used_tokens(self):
        created = self.create_invitation(email='invite@example.test', role='manager', max_uses=1)
        token = created.json()['token']
        self.authenticate(self.outsider)
        mismatch = self.client.post('/api/projects/invitations/accept/', {'token': token}, format='json')
        self.assertEqual(mismatch.status_code, 403)
        self.assertNotIn(token, mismatch.content.decode())
        invited = User.objects.create_user(username='invited', email='INVITE@example.test', password='Strong-Password-882!')
        self.authenticate(invited)
        accepted = self.client.post('/api/projects/invitations/accept/', {'token': token}, format='json')
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(ProjectMembership.objects.get(project=self.project, user=invited).role, 'manager')
        self.assertEqual(self.client.post('/api/projects/invitations/accept/', {'token': token}, format='json').status_code, 404)
        self.assertEqual(self.client.post('/api/projects/invitations/accept/', {'token': 'invalid'}, format='json').status_code, 404)
        expired = self.create_invitation(email='expired@example.test')
        invitation = ProjectInvitation.objects.get(pk=expired.json()['id'])
        ProjectInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post('/api/projects/invitations/accept/', {'token': expired.json()['token']}, format='json').status_code, 404)
        revoked = self.create_invitation(email='revoked@example.test')
        self.client.post(f'/api/projects/{self.project.pk}/invitations/{revoked.json()["id"]}/', {}, format='json')
        self.assertEqual(self.client.post('/api/projects/invitations/accept/', {'token': revoked.json()['token']}, format='json').status_code, 404)

    def test_acceptance_rolls_back_membership_and_use_when_audit_write_fails(self):
        created = self.create_invitation(email='rollback@example.test')
        invited = User.objects.create_user(username='rollback-invitee', email='rollback@example.test')
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(invited)
        with patch('projects.invitation_views.ProjectAccessAuditEvent.objects.create', side_effect=RuntimeError('audit unavailable')):
            response = client.post('/api/projects/invitations/accept/', {'token': created.json()['token']}, format='json')
        self.assertEqual(response.status_code, 500)
        invitation = ProjectInvitation.objects.get(pk=created.json()['id'])
        self.assertEqual(invitation.use_count, 0)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=invited).exists())


class ExistingMembershipMigrationTests(TransactionTestCase):
    reset_sequences = True

    migrate_from = ('projects', '0004_reveal_audit_action')
    migrate_to = ('projects', '0005_alter_projectmembership_role_projectaccessauditevent_and_more')

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_member_rows_become_managers_without_replacing_memberships_or_projects(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        UserModel = old_apps.get_model('accounts', 'User')
        ProjectModel = old_apps.get_model('projects', 'Project')
        MembershipModel = old_apps.get_model('projects', 'ProjectMembership')
        owner = UserModel.objects.create(username='migration-owner', password='hashed')
        member = UserModel.objects.create(username='migration-member', password='hashed')
        project = ProjectModel.objects.create(name='Migration preserved', creator_id=owner.pk)
        membership = MembershipModel.objects.create(project_id=project.pk, user_id=member.pk, added_by_id=owner.pk, role='member')

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        MigratedProject = new_apps.get_model('projects', 'Project')
        MigratedMembership = new_apps.get_model('projects', 'ProjectMembership')
        self.assertTrue(MigratedProject.objects.filter(pk=project.pk, creator_id=owner.pk).exists())
        migrated = MigratedMembership.objects.get(pk=membership.pk)
        self.assertEqual(migrated.user_id, member.pk)
        self.assertEqual(migrated.role, 'manager')
        self.assertEqual(MigratedMembership.objects.filter(project_id=project.pk, user_id=member.pk).count(), 1)


class ConcurrentInvitationClaimTests(TransactionTestCase):
    def test_atomic_use_claim_never_exceeds_invitation_limit(self):
        owner = User.objects.create_user(username='claim-owner', email='claim-owner@example.test')
        project = Project.objects.create(name='Claim project', creator=owner)
        token = 'concurrent-use-test-token'
        invitation = ProjectInvitation.objects.create(
            project=project, invited_email='claim@example.test', token_hash=token_digest(token),
            role='member', expires_at=timezone.now() + timedelta(hours=1), max_uses=1,
        )
        gate = Barrier(2)

        def claim():
            close_old_connections()
            try:
                gate.wait(timeout=5)
                return claim_invitation_use(invitation.pk, token_digest(token))
            except OperationalError:
                return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: claim(), range(2)))
        invitation.refresh_from_db()
        self.assertEqual(sum(results), 1)
        self.assertEqual(invitation.use_count, 1)
