import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Environment, EnvironmentVariable, Project, ProjectMembership


TEST_ENCRYPTION_KEY = base64.urlsafe_b64encode(b'T' * 32).decode('ascii')
User = get_user_model()


@override_settings(
    ENVSHARE_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
    ENVSHARE_HISTORY_ENCRYPTION_KEY=base64.urlsafe_b64encode(b'U' * 32).decode('ascii'),
)
class EnvironmentVariableApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='env-owner', password='Strong-Password-882!'
        )
        self.member = User.objects.create_user(
            username='env-member', password='Strong-Password-882!'
        )
        self.outsider = User.objects.create_user(
            username='env-outsider', password='Strong-Password-882!'
        )
        self.project = Project.objects.create(name='Env project', creator=self.owner)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            added_by=self.owner,
            role=ProjectMembership.Role.MANAGER,
        )
        self.environments = list(self.project.environments.order_by('pk'))
        self.development = self.project.environments.get(name=Environment.Name.DEVELOPMENT)
        self.staging = self.project.environments.get(name=Environment.Name.STAGING)
        self.client = APIClient()

    def authenticate_as(self, user):
        self.client.force_authenticate(user=user)

    def variable_list_url(self, environment=None):
        environment = environment or self.development
        return f'/api/projects/{self.project.pk}/environments/{environment.pk}/variables/'

    def variable_detail_url(self, variable, environment=None):
        environment = environment or variable.environment
        return f'{self.variable_list_url(environment)}{variable.pk}/'

    def create_variable(self, key='SERVICE_URL', value='https://service.example', sensitivity='standard'):
        self.authenticate_as(self.owner)
        return self.client.post(
            self.variable_list_url(),
            {'key': key, 'value': value, 'sensitivity': sensitivity},
            format='json',
        )

    def test_every_project_has_exactly_three_supported_environments(self):
        self.assertEqual(
            [environment.name for environment in self.environments],
            ['development', 'staging', 'production'],
        )
        self.assertEqual(self.project.environments.count(), 3)
        self.authenticate_as(self.owner)

        response = self.client.get(f'/api/projects/{self.project.pk}/environments/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['name'] for item in response.json()], ['development', 'staging', 'production'])
        self.assertEqual(
            self.client.post(f'/api/projects/{self.project.pk}/environments/', {}, format='json').status_code,
            405,
        )

    def test_owner_and_member_can_create_view_edit_and_delete_variables(self):
        created = self.create_variable()
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['value'], 'https://service.example')
        variable = EnvironmentVariable.objects.get(environment=self.development, key='SERVICE_URL')
        self.authenticate_as(self.member)
        listed = self.client.get(self.variable_list_url())
        detail = self.client.get(self.variable_detail_url(variable))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]['value'], 'https://service.example')
        self.assertEqual(detail.status_code, 200)

        updated = self.client.patch(
            self.variable_detail_url(variable),
            {'value': 'https://new-service.example'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['value'], 'https://new-service.example')

        deleted = self.client.delete(self.variable_detail_url(variable))
        self.assertEqual(deleted.status_code, 204)

    def test_standard_creation_does_not_require_sensitive_encryption(self):
        self.authenticate_as(self.owner)
        with self.settings(ENVSHARE_ENCRYPTION_KEY=''):
            response = self.client.post(
                self.variable_list_url(),
                {'key': 'PUBLIC_SETTING', 'value': 'visible', 'sensitivity': 'standard'},
                format='json',
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['value'], 'visible')
        self.assertEqual(response.json()['sensitivity'], 'standard')

    def test_encryption_status_is_safe_and_reflects_validity(self):
        self.authenticate_as(self.owner)
        with self.settings(ENVSHARE_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY):
            available = self.client.get('/api/projects/encryption-status/')
        self.assertEqual(available.json(), {
            'available': True, 'reason': None,
            'standard_history_available': True, 'standard_history_reason': None,
        })
        with self.settings(ENVSHARE_ENCRYPTION_KEY='bad-key-material'):
            unavailable = self.client.get('/api/projects/encryption-status/')
        self.assertEqual(unavailable.json(), {
            'available': False, 'reason': 'invalid_configuration',
            'standard_history_available': True, 'standard_history_reason': None,
        })
        self.assertNotIn('key', str(unavailable.json()).lower())
        with self.settings(ENVSHARE_HISTORY_ENCRYPTION_KEY=''):
            history_unavailable = self.client.get('/api/projects/encryption-status/')
        self.assertFalse(history_unavailable.json()['standard_history_available'])
        self.assertEqual(history_unavailable.json()['standard_history_reason'], 'not_configured')

        self.authenticate_as(self.owner)
        self.assertEqual(self.client.get(self.variable_list_url()).json(), [])

    def test_duplicate_keys_are_rejected_within_an_environment_only(self):
        first = self.create_variable(key='DATABASE_URL')
        self.assertEqual(first.status_code, 201)

        self.authenticate_as(self.member)
        duplicate = self.client.post(
            self.variable_list_url(),
            {'key': 'DATABASE_URL', 'value': 'another', 'sensitivity': 'standard'},
            format='json',
        )
        other_environment = self.client.post(
            self.variable_list_url(self.staging),
            {'key': 'DATABASE_URL', 'value': 'staging-value', 'sensitivity': 'standard'},
            format='json',
        )

        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('key', duplicate.json())
        self.assertEqual(other_environment.status_code, 201)

    def test_invalid_keys_and_sensitivity_are_rejected(self):
        self.authenticate_as(self.owner)
        invalid_key = self.client.post(
            self.variable_list_url(),
            {'key': 'bad key', 'value': 'value', 'sensitivity': 'standard'},
            format='json',
        )
        invalid_classification = self.client.post(
            self.variable_list_url(),
            {'key': 'VALID_KEY', 'value': 'value', 'sensitivity': 'secret'},
            format='json',
        )

        self.assertEqual(invalid_key.status_code, 400)
        self.assertIn('key', invalid_key.json())
        self.assertEqual(invalid_classification.status_code, 400)
        self.assertIn('sensitivity', invalid_classification.json())

    def test_sensitive_value_is_encrypted_at_rest_and_masked_in_normal_apis(self):
        plaintext = 'sensitive-test-plaintext-9x7m'
        created = self.create_variable(
            key='API_TOKEN',
            value=plaintext,
            sensitivity='sensitive',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['value'], '••••••••')
        variable = EnvironmentVariable.objects.get(environment=self.development, key='API_TOKEN')

        # Inspect the persisted database field directly: the original plaintext must not be present.
        stored_value = EnvironmentVariable.objects.filter(pk=variable.pk).values_list('value', flat=True).get()
        self.assertTrue(stored_value.startswith('aesgcm:v1:'))
        self.assertNotIn(plaintext, stored_value)

        self.authenticate_as(self.member)
        list_response = self.client.get(self.variable_list_url())
        detail_response = self.client.get(self.variable_detail_url(variable))
        self.assertEqual(list_response.json()[0]['value'], '••••••••')
        self.assertEqual(detail_response.json()['value'], '••••••••')
        self.assertNotIn(plaintext, list_response.content.decode())
        self.assertNotIn(plaintext, detail_response.content.decode())

        reveal_response = self.client.post(
            f'{self.variable_detail_url(variable)}reveal/',
            {},
            format='json',
        )
        self.assertEqual(reveal_response.status_code, 200)
        self.assertEqual(reveal_response.json(), {'key': 'API_TOKEN', 'value': plaintext})

    def test_sensitive_key_rename_and_classification_changes_reencrypt_correctly(self):
        created = self.create_variable('PRIVATE_KEY', 'keep-this-value', 'sensitive')
        variable = EnvironmentVariable.objects.get(pk=created.json()['id'])
        old_ciphertext = variable.value
        self.authenticate_as(self.member)

        renamed = self.client.patch(
            self.variable_detail_url(variable),
            {'key': 'RENAMED_PRIVATE_KEY'},
            format='json',
        )
        variable.refresh_from_db()
        self.assertEqual(renamed.status_code, 200)
        self.assertNotEqual(variable.value, old_ciphertext)
        self.assertEqual(renamed.json()['value'], '••••••••')

        standard = self.client.patch(
            self.variable_detail_url(variable),
            {'sensitivity': 'standard'},
            format='json',
        )
        variable.refresh_from_db()
        self.assertEqual(standard.status_code, 200)
        self.assertEqual(variable.value, 'keep-this-value')
        self.assertEqual(standard.json()['value'], 'keep-this-value')

        sensitive_again = self.client.patch(
            self.variable_detail_url(variable),
            {'sensitivity': 'sensitive'},
            format='json',
        )
        variable.refresh_from_db()
        self.assertEqual(sensitive_again.status_code, 200)
        self.assertNotIn('keep-this-value', variable.value)
        self.assertEqual(sensitive_again.json()['value'], '••••••••')

    def test_unauthorized_users_cannot_access_any_environment_or_variable_endpoint(self):
        created = self.create_variable('PRIVATE', 'private-value')
        variable = EnvironmentVariable.objects.get(pk=created.json()['id'])
        self.authenticate_as(self.outsider)

        responses = [
            self.client.get(f'/api/projects/{self.project.pk}/environments/'),
            self.client.get(self.variable_list_url()),
            self.client.post(
                self.variable_list_url(),
                {'key': 'OUTSIDER', 'value': 'attempt', 'sensitivity': 'standard'},
                format='json',
            ),
            self.client.get(self.variable_detail_url(variable)),
            self.client.patch(self.variable_detail_url(variable), {'value': 'attempt'}, format='json'),
            self.client.delete(self.variable_detail_url(variable)),
            self.client.post(f'{self.variable_detail_url(variable)}reveal/', {}, format='json'),
        ]

        self.assertTrue(all(response.status_code == 404 for response in responses))
        self.assertTrue(EnvironmentVariable.objects.filter(pk=variable.pk).exists())

    def test_sensitive_reveal_rejects_plaintext_classification(self):
        created = self.create_variable()
        variable = EnvironmentVariable.objects.get(pk=created.json()['id'])
        self.authenticate_as(self.member)

        response = self.client.post(
            f'{self.variable_detail_url(variable)}reveal/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn('https://service.example', response.content.decode())

    def test_malformed_ciphertext_and_missing_key_fail_without_revealing_plaintext(self):
        plaintext = 'do-not-include-this-value-in-errors'
        created = self.create_variable('TAMPERED', plaintext, 'sensitive')
        variable = EnvironmentVariable.objects.get(pk=created.json()['id'])
        EnvironmentVariable.objects.filter(pk=variable.pk).update(value='aesgcm:v1:broken')
        self.authenticate_as(self.owner)

        tampered = self.client.post(
            f'{self.variable_detail_url(variable)}reveal/', {}, format='json'
        )
        self.assertEqual(tampered.status_code, 503)
        self.assertNotIn(plaintext, tampered.content.decode())

        with self.settings(ENVSHARE_ENCRYPTION_KEY=''):
            missing_key = self.client.post(
                f'{self.variable_list_url()}',
                {'key': 'NO_KEY', 'value': plaintext, 'sensitivity': 'sensitive'},
                format='json',
            )
        self.assertEqual(missing_key.status_code, 503)
        self.assertNotIn(plaintext, missing_key.content.decode())

    def test_environment_ids_cannot_be_crossed_between_projects(self):
        other_project = Project.objects.create(name='Other project', creator=self.outsider)
        other_environment = other_project.environments.get(name=Environment.Name.DEVELOPMENT)
        self.authenticate_as(self.owner)

        response = self.client.get(self.variable_list_url(other_environment))

        self.assertEqual(response.status_code, 404)
