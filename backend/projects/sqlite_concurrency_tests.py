from concurrent.futures import ThreadPoolExecutor
import base64
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import Environment, EnvironmentVariableVersion, Project


User = get_user_model()
TEST_KEY = base64.urlsafe_b64encode(b'Q' * 32).decode('ascii')


@skipUnless(connection.vendor == 'sqlite', 'SQLite-specific write-lock fallback test')
@override_settings(
    ENVSHARE_ENCRYPTION_KEY=TEST_KEY,
    ENVSHARE_HISTORY_ENCRYPTION_KEY=base64.urlsafe_b64encode(b'Z' * 32).decode('ascii'),
)
class SQLiteConcurrentVariableUpdateTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_updates_never_duplicate_version_numbers_or_partially_commit(self):
        owner = User.objects.create_user(username='sqlite-lock-owner')
        project = Project.objects.create(name='SQLite lock test', creator=owner)
        environment = project.environments.get(name=Environment.Name.DEVELOPMENT)
        url = f'/api/projects/{project.pk}/environments/{environment.pk}/variables/'
        client = APIClient()
        client.force_authenticate(owner)
        created = client.post(url, {'key': 'LOCKED_VALUE', 'value': 'before', 'sensitivity': 'standard'}, format='json')
        self.assertEqual(created.status_code, 201)
        variable_id = created.json()['id']
        barrier = Barrier(2)

        def update(value):
            close_old_connections()
            try:
                actor = User.objects.get(pk=owner.pk)
                local = APIClient()
                local.force_authenticate(actor)
                barrier.wait(timeout=10)
                return local.patch(f'{url}{variable_id}/', {'value': value}, format='json')
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(update, ('left-update', 'right-update')))
        self.assertTrue(all(response.status_code in (200, 409) for response in responses))
        conflicts = [response for response in responses if response.status_code == 409]
        self.assertTrue(all(
            response.json() == {
                'detail': 'The request conflicted with another database write. Retry the operation.',
            }
            for response in conflicts
        ))
        committed = sum(response.status_code == 200 for response in responses)
        self.assertGreaterEqual(committed, 1)
        numbers = list(EnvironmentVariableVersion.objects.filter(
            variable_id_snapshot=variable_id,
        ).order_by('version_number').values_list('version_number', flat=True))
        self.assertEqual(numbers, list(range(1, committed + 2)))
