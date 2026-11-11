import os

from django.core.management import BaseCommand, CommandError, call_command


class Command(BaseCommand):
    help = 'Validate that this process has loaded the complete production configuration.'

    def handle(self, *args, **options):
        if os.environ.get('DJANGO_ENV', '').strip().lower() != 'production':
            raise CommandError('Set DJANGO_ENV=production before running the production validation command.')
        # Settings import performs strict validation. Django's deployment checks add
        # framework-level checks without printing any configured secret values.
        call_command('check', deploy=True)
        self.stdout.write(self.style.SUCCESS('Production settings passed Django deployment checks.'))
