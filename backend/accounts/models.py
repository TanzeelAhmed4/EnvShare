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
