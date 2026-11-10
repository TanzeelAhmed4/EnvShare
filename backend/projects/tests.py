from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Project, ProjectMembership
from .permissions import can_access_project, can_edit_project_data


User = get_user_model()


class ProjectApiTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', email='creator@example.com', password='Strong-Password-882!'
        )
        self.member = User.objects.create_user(
            username='member', email='member@example.com', password='Strong-Password-882!'
        )
        self.outsider = User.objects.create_user(
            username='outsider', email='outsider@example.com', password='Strong-Password-882!'
        )
        self.project = Project.objects.create(
            name='Payments API', description='Payment services', creator=self.creator
        )
        self.client = APIClient()

    def authenticate_as(self, user):
        self.client.force_authenticate(user=user)

    def test_authenticated_user_can_create_project(self):
        self.authenticate_as(self.creator)

        response = self.client.post('/api/projects/', {
            'name': 'Internal tools',
            'description': 'Shared engineering utilities',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        created = Project.objects.get(name='Internal tools')
        self.assertEqual(created.creator, self.creator)
        self.assertEqual(response.json()['creator_id'], self.creator.pk)
        self.assertEqual(response.json()['member_count'], 0)
        self.assertIsNotNone(response.json()['created_at'])
        self.assertIsNotNone(response.json()['updated_at'])

    def test_project_creation_requires_authentication_and_a_name(self):
        anonymous_response = self.client.post('/api/projects/', {'name': 'No access'}, format='json')
        self.assertEqual(anonymous_response.status_code, 403)

        self.authenticate_as(self.creator)
        invalid_response = self.client.post('/api/projects/', {'description': 'Missing name'}, format='json')
        self.assertEqual(invalid_response.status_code, 400)
        self.assertIn('name', invalid_response.json())

    def test_user_sees_only_projects_they_created_or_joined(self):
        member_project = Project.objects.create(name='Joined project', creator=self.outsider)
        ProjectMembership.objects.create(project=member_project, user=self.member, added_by=self.outsider)
        private_project = Project.objects.create(name='Private project', creator=self.outsider)

        self.authenticate_as(self.creator)
        creator_projects = self.client.get('/api/projects/').json()
        self.assertEqual([project['id'] for project in creator_projects], [self.project.pk])

        self.authenticate_as(self.member)
        member_projects = self.client.get('/api/projects/').json()
        self.assertEqual([project['id'] for project in member_projects], [member_project.pk])

        self.authenticate_as(self.outsider)
        outsider_projects = self.client.get('/api/projects/').json()
        self.assertEqual(
            {project['id'] for project in outsider_projects},
            {member_project.pk, private_project.pk},
        )

    def test_creator_can_add_registered_user_and_member_can_access_project(self):
        self.authenticate_as(self.creator)

        response = self.client.post(
            f'/api/projects/{self.project.pk}/members/',
            {'username': self.member.username, 'role': ProjectMembership.Role.MANAGER},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['user_id'], self.member.pk)
        self.assertEqual(response.json()['role'], ProjectMembership.Role.MANAGER)
        membership = ProjectMembership.objects.get(project=self.project, user=self.member)
        self.assertEqual(membership.added_by, self.creator)

        self.authenticate_as(self.member)
        self.assertEqual(self.client.get('/api/projects/').json()[0]['id'], self.project.pk)
        detail = self.client.get(f'/api/projects/{self.project.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(can_access_project(self.member, self.project))
        self.assertTrue(can_edit_project_data(self.member, self.project))

    def test_creator_can_list_and_remove_members(self):
        membership = ProjectMembership.objects.create(
            project=self.project, user=self.member, added_by=self.creator
        )
        self.authenticate_as(self.creator)

        listed = self.client.get(f'/api/projects/{self.project.pk}/members/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]['username'], self.member.username)

        removed = self.client.delete(
            f'/api/projects/{self.project.pk}/members/{self.member.pk}/'
        )
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(ProjectMembership.objects.filter(pk=membership.pk).exists())

        self.authenticate_as(self.member)
        self.assertEqual(self.client.get(f'/api/projects/{self.project.pk}/').status_code, 404)

    def test_creator_cannot_add_self_or_add_unknown_or_duplicate_users(self):
        self.authenticate_as(self.creator)
        url = f'/api/projects/{self.project.pk}/members/'

        self_response = self.client.post(url, {'username': self.creator.username}, format='json')
        unknown_response = self.client.post(url, {'username': 'missing-user'}, format='json')
        self.assertEqual(self_response.status_code, 400)
        self.assertEqual(unknown_response.status_code, 400)

        ProjectMembership.objects.create(project=self.project, user=self.member, added_by=self.creator, role=ProjectMembership.Role.MANAGER)
        duplicate_response = self.client.post(url, {'username': 'MEMBER'}, format='json')
        self.assertEqual(duplicate_response.status_code, 400)
        self.assertIn('username', duplicate_response.json())

    def test_non_members_cannot_view_project_or_manage_its_members(self):
        self.authenticate_as(self.outsider)

        detail = self.client.get(f'/api/projects/{self.project.pk}/')
        add = self.client.post(
            f'/api/projects/{self.project.pk}/members/',
            {'username': self.member.username},
            format='json',
        )
        remove = self.client.delete(
            f'/api/projects/{self.project.pk}/members/{self.member.pk}/'
        )

        self.assertEqual(detail.status_code, 404)
        self.assertEqual(add.status_code, 403)
        self.assertEqual(remove.status_code, 403)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project).exists())

    def test_members_cannot_add_or_remove_other_members(self):
        ProjectMembership.objects.create(project=self.project, user=self.member, added_by=self.creator, role=ProjectMembership.Role.MANAGER)
        ProjectMembership.objects.create(project=self.project, user=self.outsider, added_by=self.creator)
        self.authenticate_as(self.member)

        add = self.client.post(
            f'/api/projects/{self.project.pk}/members/',
            {'username': 'new-user'},
            format='json',
        )
        remove = self.client.delete(
            f'/api/projects/{self.project.pk}/members/{self.outsider.pk}/'
        )

        self.assertEqual(add.status_code, 403)
        self.assertEqual(remove.status_code, 403)
        self.assertTrue(ProjectMembership.objects.filter(project=self.project, user=self.outsider).exists())

    def test_creator_and_members_can_edit_project_data_but_outsiders_cannot(self):
        ProjectMembership.objects.create(project=self.project, user=self.member, added_by=self.creator, role=ProjectMembership.Role.MANAGER)

        self.assertTrue(can_edit_project_data(self.creator, self.project))
        self.assertTrue(can_edit_project_data(self.member, self.project))
        self.assertFalse(can_edit_project_data(self.outsider, self.project))
        self.assertFalse(can_edit_project_data(None, self.project))


from .environment_tests import EnvironmentVariableApiTests  # noqa: F401,E402
from .env_import_tests import EnvImportApiTests, EnvImportParserTests  # noqa: F401,E402
from .audit_tests import EnvironmentVariableAuditTests  # noqa: F401,E402
from .encryption_tests import EncryptionConfigurationTests  # noqa: F401,E402
from .role_invitation_tests import ProjectRoleAndInvitationTests  # noqa: F401,E402
from .role_invitation_tests import ExistingMembershipMigrationTests  # noqa: F401,E402
from .role_invitation_tests import ConcurrentInvitationClaimTests  # noqa: F401,E402
from .version_tests import EnvironmentVariableVersionTests  # noqa: F401,E402
