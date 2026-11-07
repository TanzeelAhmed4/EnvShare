from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Environment, Project


@receiver(post_save, sender=Project)
def create_project_environments(sender, instance, created, **kwargs):
    if created:
        for name, _label in Environment.Name.choices:
            Environment.objects.get_or_create(project=instance, name=name)
