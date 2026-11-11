from django.db.models import Max

from .encryption import encrypt_historical_value
from .models import EnvironmentVariableVersion


def create_variable_version(*, variable, action, actor, plaintext):
    """Create an encrypted snapshot; callers must include this in the mutation transaction."""
    current_max = EnvironmentVariableVersion.objects.filter(
        variable_id_snapshot=variable.pk,
    ).aggregate(value=Max('version_number'))['value'] or 0
    version = EnvironmentVariableVersion(
        project=variable.environment.project,
        project_id_snapshot=variable.environment.project_id,
        environment=variable.environment,
        environment_id_snapshot=variable.environment_id,
        variable=variable,
        variable_id_snapshot=variable.pk,
        variable_key=variable.key,
        version_number=current_max + 1,
        encrypted_value='',
        sensitivity=variable.sensitivity,
        action=action,
        actor=actor,
        actor_username=actor.get_username(),
    )
    version.encrypted_value = encrypt_historical_value(plaintext, version)
    version.save(force_insert=True)
    return version
