from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

# Create your models here.
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        constraints = [
            models.UniqueConstraint(Lower('username'), name='accounts_user_username_ci_uniq'),
            models.UniqueConstraint(
                Lower('email'),
                condition=~Q(email=''),
                name='accounts_user_email_ci_uniq',
            ),
        ]


class AuthenticationAuditEvent(models.Model):
    class Action(models.TextChoices):
        REGISTRATION = 'registration', 'Registration'
        LOGIN_SUCCESS = 'login_success', 'Login success'
        LOGOUT = 'logout', 'Logout'

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='authentication_audit_events',
    )
    username_snapshot = models.CharField(max_length=150)
    action = models.CharField(max_length=20, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=('user', '-created_at'), name='auth_audit_user_time_idx')]
