import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .env_import import parse_env_content
from .models import Environment, EnvironmentVariable, Project, ProjectMembership


TEST_KEY = base64.urlsafe_b64encode(b'I' * 32).decode('ascii')
User = get_user_model()


class EnvImportParserTests(TestCase):
    def test_comments_blanks_whitespace_quotes_and_additional_equals(self):
        entries, errors = parse_env_content(
            '  # ignored\n\n  API_KEY = " value = with equals "  \n'
            "TOKEN='single quoted'\nURL=https://host/path?a=b\nPLAIN=  spaced value  \n"
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            [(item['key'], item['value']) for item in entries],
            [
                ('API_KEY', ' value = with equals '),
                ('TOKEN', 'single quoted'),
                ('URL', 'https://host/path?a=b'),
                ('PLAIN', 'spaced value'),
            ],
        )

    def test_invalid_lines_are_reported_without_echoing_values(self):
        entries, errors = parse_env_content('MISSING_EQUALS\nBAD KEY=secret-content\nX="unclosed-secret')
        self.assertEqual(entries, [])
        self.assertEqual([item['line'] for item in errors], [1, 2, 3])
        self.assertNotIn('secret-content', str(errors))

    def test_duplicate_keys_are_reported(self):
        entries, errors = parse_env_content('A=one\nA=two')
        self.assertEqual(len(entries), 1)
        self.assertEqual(errors, [{'line': 2, 'message': 'Duplicate key in imported text.'}])


@override_settings(ENVSHARE_ENCRYPTION_KEY=TEST_KEY)
class EnvImportApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='import-owner', password='Strong-Password-882!')
        self.member = User.objects.create_user(username='import-member', password='Strong-Password-882!')
        self.outsider = User.objects.create_user(username='import-outsider', password='Strong-Password-882!')
        self.project = Project.objects.create(name='Import project', creator=self.owner)
        ProjectMembership.objects.create(project=self.project, user=self.member, added_by=self.owner)
        self.environment = self.project.environments.get(name=Environment.Name.DEVELOPMENT)
        self.client = APIClient()

    def url(self, action):
        return f'/api/projects/{self.project.pk}/environments/{self.environment.pk}/import/{action}/'

    def payload(self, content, **extra):
        return {'content': content, **extra}

    def test_preview_returns_exact_classifications_and_does_not_save(self):
        EnvironmentVariable.objects.create(
            environment=self.environment, key='OLD', value='before', sensitivity='standard'
        )
        EnvironmentVariable.objects.create(
            environment=self.environment, key='SAME', value='keep', sensitivity='standard'
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            self.url('preview'),
            self.payload('NEW=private-new\nOLD=after\nSAME=keep', classifications={'NEW': 'sensitive'}),
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['classification'] for item in response.json()['preview']],
            ['New', 'Update', 'Unchanged'],
        )
        self.assertEqual(response.json()['preview'][0]['new_value'], '••••••••')
        self.assertEqual(response.json()['preview'][1]['old_value'], 'before')
        self.assertEqual(response.json()['preview'][1]['new_value'], 'after')
        self.assertEqual(EnvironmentVariable.objects.count(), 2)

    def test_confirm_is_required_and_import_saves_only_after_confirmation(self):
        self.client.force_authenticate(user=self.owner)
        data = self.payload('NEW_VALUE=secret-to-store', classifications={'NEW_VALUE': 'sensitive'})

        preview = self.client.post(self.url('preview'), data, format='json')
        data_with_token = {**data, 'preview_token': preview.json()['preview_token']}
        no_confirm = self.client.post(self.url('confirm'), data_with_token, format='json')
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(no_confirm.status_code, 400)
        self.assertFalse(EnvironmentVariable.objects.exists())

        confirmed = self.client.post(
            self.url('confirm'), {**data_with_token, 'confirm': True}, format='json',
        )
        variable = EnvironmentVariable.objects.get(environment=self.environment, key='NEW_VALUE')
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json(), {'created': 1, 'updated': 0, 'unchanged': 0})
        self.assertTrue(variable.value.startswith('aesgcm:v1:'))
        self.assertNotIn('secret-to-store', variable.value)
        self.assertNotIn('secret-to-store', confirmed.content.decode())

    def test_unclassified_new_value_stays_masked_and_cannot_be_saved(self):
        self.client.force_authenticate(user=self.owner)
        content = 'POSSIBLE_SECRET=do-not-return-this-value'

        preview = self.client.post(self.url('preview'), self.payload(content), format='json')
        confirm = self.client.post(
            self.url('confirm'),
            self.payload(content, confirm=True, preview_token=preview.json()['preview_token']),
            format='json',
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()['preview'][0]['new_value'], '••••••••')
        self.assertNotIn('do-not-return-this-value', preview.content.decode())
        self.assertEqual(confirm.status_code, 400)
        self.assertFalse(EnvironmentVariable.objects.exists())

    def test_updates_preserve_existing_sensitivity_and_encrypt_existing_sensitive_values(self):
        sensitive = EnvironmentVariable.objects.create(
            environment=self.environment,
            key='PRIVATE',
            value='placeholder',
            sensitivity='sensitive',
        )
        from .encryption import encrypt_value
        sensitive.value = encrypt_value('old secret', self.environment, 'PRIVATE')
        sensitive.save(update_fields=['value'])
        EnvironmentVariable.objects.create(
            environment=self.environment, key='PUBLIC', value='old public', sensitivity='standard'
        )
        self.client.force_authenticate(user=self.member)

        preview = self.client.post(
            self.url('preview'),
            self.payload('PRIVATE=new secret\nPUBLIC=new public\nADDED=visible', classifications={'ADDED': 'standard'}),
            format='json',
        )
        self.assertEqual(preview.status_code, 200)
        preview_items = preview.json()['preview']
        self.assertEqual(preview_items[0]['old_value'], '••••••••')
        self.assertEqual(preview_items[0]['new_value'], '••••••••')
        self.assertNotIn('old secret', preview.content.decode())
        self.assertNotIn('new secret', preview.content.decode())

        saved = self.client.post(
            self.url('confirm'),
            self.payload(
                'PRIVATE=new secret\nPUBLIC=new public\nADDED=visible',
                classifications={'ADDED': 'standard'},
                confirm=True,
                preview_token=preview.json()['preview_token'],
            ),
            format='json',
        )
        sensitive.refresh_from_db()
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(sensitive.sensitivity, 'sensitive')
        self.assertTrue(sensitive.value.startswith('aesgcm:v1:'))
        self.assertNotIn('new secret', sensitive.value)
        self.assertEqual(EnvironmentVariable.objects.get(key='PUBLIC').sensitivity, 'standard')
        self.assertEqual(EnvironmentVariable.objects.get(key='ADDED').sensitivity, 'standard')

    def test_invalid_lines_block_confirmation_and_permissions_are_enforced(self):
        self.client.force_authenticate(user=self.owner)
        bad = self.client.post(self.url('preview'), self.payload('BAD KEY=never-echo-this'), format='json')
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(bad.json()['invalid_lines'][0]['line'], 1)
        self.assertNotIn('never-echo-this', bad.content.decode())
        blocked = self.client.post(
            self.url('confirm'),
            self.payload(
                'BAD KEY=never-echo-this',
                confirm=True,
                preview_token=bad.json()['preview_token'],
            ),
            format='json',
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertFalse(EnvironmentVariable.objects.exists())

        self.client.force_authenticate(user=self.outsider)
        denied_preview = self.client.post(self.url('preview'), self.payload('A=1'), format='json')
        denied_confirm = self.client.post(self.url('confirm'), self.payload('A=1', confirm=True), format='json')
        self.assertEqual(denied_preview.status_code, 404)
        self.assertEqual(denied_confirm.status_code, 404)
        self.assertFalse(EnvironmentVariable.objects.exists())

    def test_confirmation_rejects_changed_environment_or_changed_import_text(self):
        variable = EnvironmentVariable.objects.create(
            environment=self.environment,
            key='EXISTING',
            value='before',
            sensitivity='standard',
        )
        self.client.force_authenticate(user=self.owner)
        content = 'EXISTING=reviewed-value'
        preview = self.client.post(self.url('preview'), self.payload(content), format='json')
        token = preview.json()['preview_token']
        variable.value = 'concurrent-value'
        variable.save(update_fields=['value', 'updated_at'])

        stale = self.client.post(
            self.url('confirm'),
            self.payload(content, confirm=True, preview_token=token),
            format='json',
        )

        self.assertEqual(stale.status_code, 409)
        self.assertNotIn('concurrent-value', stale.content.decode())
        variable.refresh_from_db()
        self.assertEqual(variable.value, 'concurrent-value')
        self.assertEqual(EnvironmentVariable.objects.count(), 1)

        fresh_preview = self.client.post(self.url('preview'), self.payload(content), format='json')
        tampered = self.client.post(
            self.url('confirm'),
            self.payload('EXISTING=unreviewed-value', confirm=True,
                         preview_token=fresh_preview.json()['preview_token']),
            format='json',
        )
        self.assertEqual(tampered.status_code, 409)
        variable.refresh_from_db()
        self.assertEqual(variable.value, 'concurrent-value')

    def test_preview_token_does_not_contain_imported_sensitive_plaintext(self):
        self.client.force_authenticate(user=self.owner)
        secret = 'private-import-preview-value-9284'
        response = self.client.post(
            self.url('preview'),
            self.payload('PRIVATE_TOKEN=' + secret, classifications={'PRIVATE_TOKEN': 'sensitive'}),
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(secret, response.json()['preview_token'])

    def test_confirmation_without_a_preview_token_does_not_write(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            self.url('confirm'),
            self.payload('NEVER_REVIEWED=value', confirm=True),
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(EnvironmentVariable.objects.exists())
