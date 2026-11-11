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
        ADMIN = 'admin', 'Admin'
        MANAGER = 'manager', 'Manager'
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


class ProjectInvitation(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invitations')
    invited_email = models.EmailField(max_length=254)
    token_hash = models.CharField(max_length=64, unique=True)
    role = models.CharField(max_length=16, choices=ProjectMembership.Role.choices)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_project_invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    max_uses = models.PositiveIntegerField(default=1)
    use_count = models.PositiveIntegerField(default=0)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=('project', 'expires_at'), name='invite_project_exp_idx')]
        constraints = [models.CheckConstraint(condition=models.Q(max_uses__gte=1), name='invite_max_uses_positive')]


class ProjectAccessAuditEvent(models.Model):
    class Action(models.TextChoices):
        PROJECT_CREATED = 'project_created', 'Project created'
        MEMBERSHIP_ADDED = 'membership_added', 'Member added'
        INVITATION_CREATED = 'invitation_created', 'Invitation created'
        INVITATION_REVOKED = 'invitation_revoked', 'Invitation revoked'
        INVITATION_ACCEPTED = 'invitation_accepted', 'Invitation accepted'
        ROLE_CHANGED = 'role_changed', 'Membership role changed'
        MEMBER_REMOVED = 'member_removed', 'Member removed'

    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, related_name='access_events')
    project_id_snapshot = models.PositiveBigIntegerField(default=0)
    project_name_snapshot = models.CharField(max_length=120, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_username = models.CharField(max_length=150)
    action = models.CharField(max_length=32, choices=Action.choices)
    target_email = models.EmailField(max_length=254, blank=True)
    target_username = models.CharField(max_length=150, blank=True)
    role_before = models.CharField(max_length=16, blank=True)
    role_after = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [
            models.Index(fields=('project', '-created_at'), name='access_audit_proj_time_idx'),
            models.Index(fields=('project', 'action', '-created_at'), name='access_audit_action_idx'),
            models.Index(fields=('project', 'actor_username'), name='access_audit_actor_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.project_id:
            self.project_id_snapshot = self.project_id
            self.project_name_snapshot = self.project.name
        super().save(*args, **kwargs)


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
        REVEALED = 'revealed', 'Revealed'
        RESTORED = 'restored', 'Restored'
        VERSION_ACCESSED = 'version_accessed', 'Historical value accessed'
        VERSION_COMPARED = 'version_compared', 'Sensitive versions compared'
        BULK_IMPORTED = 'bulk_imported', 'Bulk import'

    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, related_name='audit_events')
    project_id_snapshot = models.PositiveBigIntegerField(default=0)
    environment = models.ForeignKey(
        Environment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
    )
    variable_id = models.PositiveBigIntegerField()
    variable_key = models.CharField(max_length=255)
    action = models.CharField(max_length=20, choices=Action.choices)
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
            models.Index(fields=('project', 'action', '-created_at'), name='audit_project_action_idx'),
            models.Index(fields=('project', 'actor', '-created_at'), name='audit_project_actor_idx'),
            models.Index(fields=('project', 'variable_id'), name='audit_project_variable_idx'),
            models.Index(fields=('project', 'variable_key'), name='audit_project_key_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.project_id:
            self.project_id_snapshot = self.project_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_action_display()} {self.variable_key} by {self.actor_username}'


class EnvironmentVariableVersion(models.Model):
    class Action(models.TextChoices):
        CREATED = 'created', 'Created'
        UPDATED = 'updated', 'Updated'
        RESTORED = 'restored', 'Restored'
        DELETED = 'deleted', 'Deleted'

    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, related_name='variable_versions')
    project_id_snapshot = models.PositiveBigIntegerField(default=0)
    environment = models.ForeignKey(
        Environment, on_delete=models.SET_NULL, null=True, related_name='variable_versions'
    )
    environment_id_snapshot = models.PositiveBigIntegerField()
    variable = models.ForeignKey(
        EnvironmentVariable, on_delete=models.SET_NULL, null=True, related_name='versions'
    )
    variable_id_snapshot = models.PositiveBigIntegerField()
    variable_key = models.CharField(max_length=255)
    version_number = models.PositiveIntegerField()
    encrypted_value = models.TextField()
    sensitivity = models.CharField(max_length=16, choices=EnvironmentVariable.Sensitivity.choices)
    action = models.CharField(max_length=16, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='environment_variable_versions',
    )
    actor_username = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-version_number', '-pk')
        constraints = [
            models.UniqueConstraint(
                fields=('variable_id_snapshot', 'version_number'),
                name='unique_variable_version_number',
            ),
        ]
        indexes = [
            models.Index(
                fields=('project', 'environment_id_snapshot', 'variable_id_snapshot', 'version_number'),
                name='variable_version_scope_idx',
            ),
        ]

    def __str__(self):
        return f'{self.variable_key} v{self.version_number} ({self.get_action_display()})'
