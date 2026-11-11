from django.db.models import F

from .models import Environment, Project


def lock_environment_for_write(environment_id):
    """Serialize environment mutations on PostgreSQL and acquire SQLite's write lock early."""
    Environment.objects.filter(pk=environment_id).update(updated_at=F('updated_at'))


def lock_project_for_write(project_id):
    """Serialize project membership/invitation mutations and their audit rows."""
    Project.objects.filter(pk=project_id).update(updated_at=F('updated_at'))
