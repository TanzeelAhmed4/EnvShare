from django.conf import settings
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_projects',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at', '-created_at')

    def __str__(self):
        return self.name


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        MEMBER = 'member', 'Member'

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='project_memberships',
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='added_project_memberships',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at', 'pk')
        constraints = [
            models.UniqueConstraint(
                fields=('project', 'user'),
                name='unique_project_member',
            ),
        ]

    def __str__(self):
        return f'{self.user} on {self.project} ({self.get_role_display()})'


class Environment(models.Model):
    class Name(models.TextChoices):
        DEVELOPMENT = 'development', 'Development'
        STAGING = 'staging', 'Staging'
        PRODUCTION = 'production', 'Production'

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='environments',
    )
    name = models.CharField(max_length=16, choices=Name.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('project', 'name'),
                name='unique_environment_name_per_project',
            ),
        ]

    def __str__(self):
        return f'{self.project} / {self.get_name_display()}'


class EnvironmentVariable(models.Model):
    class Sensitivity(models.TextChoices):
        STANDARD = 'standard', 'Standard'
        SENSITIVE = 'sensitive', 'Sensitive'

    environment = models.ForeignKey(
        Environment,
        on_delete=models.CASCADE,
        related_name='variables',
    )
    key = models.CharField(max_length=255)
    # Standard values are plaintext; Sensitive values are AES-GCM envelopes.
    value = models.TextField()
    sensitivity = models.CharField(
        max_length=16,
        choices=Sensitivity.choices,
        default=Sensitivity.STANDARD,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('key', 'pk')
        constraints = [
            models.UniqueConstraint(
                fields=('environment', 'key'),
                name='unique_variable_key_per_environment',
            ),
        ]

    def __str__(self):
        return f'{self.environment} / {self.key}'


class EnvironmentVariableAuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATED = 'created', 'Created'
        UPDATED = 'updated', 'Updated'
        DELETED = 'deleted', 'Deleted'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='audit_events')
    environment = models.ForeignKey(
        Environment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
    )
    variable_id = models.PositiveBigIntegerField()
    variable_key = models.CharField(max_length=255)
    action = models.CharField(max_length=16, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='environment_variable_audit_events',
    )
    actor_username = models.CharField(max_length=150)
    project_name = models.CharField(max_length=120)
    environment_name = models.CharField(max_length=16)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [
            models.Index(fields=('project', '-created_at'), name='audit_project_time_idx'),
            models.Index(fields=('environment', '-created_at'), name='audit_env_time_idx'),
        ]

    def __str__(self):
        return f'{self.get_action_display()} {self.variable_key} by {self.actor_username}'
