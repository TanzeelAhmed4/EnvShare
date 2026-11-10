from .models import EnvironmentVariable, EnvironmentVariableAuditEvent


REDACTED = '[REDACTED]'
_MISSING = object()


def record_variable_audit(
    *,
    action,
    actor,
    environment,
    variable_id,
    key,
    sensitivity,
    key_before=_MISSING,
    sensitivity_before=_MISSING,
    value_before=_MISSING,
    value_after=_MISSING,
    sensitivity_before_for_value=None,
    sensitivity_after_for_value=None,
    extra_changes=None,
):
    """Persist a variable event while redacting values if either state is Sensitive."""
    project = environment.project
    changes = {}

    if key_before is not _MISSING and key_before != key:
        changes['key'] = {'before': key_before, 'after': key}
    elif action == EnvironmentVariableAuditEvent.Action.CREATED:
        changes['key'] = {'before': None, 'after': key}

    if sensitivity_before is not _MISSING and sensitivity_before != sensitivity:
        changes['sensitivity'] = {'before': sensitivity_before, 'after': sensitivity}
    elif action == EnvironmentVariableAuditEvent.Action.CREATED:
        changes['sensitivity'] = {'before': None, 'after': sensitivity}

    if value_before is not _MISSING or value_after is not _MISSING:
        before_sensitivity = (
            sensitivity_before_for_value
            if sensitivity_before_for_value is not None
            else sensitivity_before if sensitivity_before is not _MISSING else sensitivity
        )
        after_sensitivity = (
            sensitivity_after_for_value
            if sensitivity_after_for_value is not None
            else sensitivity
        )
        protected = (
            before_sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE
            or after_sensitivity == EnvironmentVariable.Sensitivity.SENSITIVE
        )
        before = None if value_before is _MISSING else REDACTED if protected else value_before
        after = None if value_after is _MISSING else REDACTED if protected else value_after
        changes['value'] = {'before': before, 'after': after}

    if extra_changes:
        changes.update(extra_changes)

    return EnvironmentVariableAuditEvent.objects.create(
        project=project,
        environment=environment,
        variable_id=variable_id,
        variable_key=key,
        action=action,
        actor=actor,
        actor_username=actor.get_username(),
        project_name=project.name,
        environment_name=environment.name,
        changes=changes,
    )
