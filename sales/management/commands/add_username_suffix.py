from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = "Append '@digiserve' to all usernames without the suffix"

    def handle(self, *args, **kwargs):
        users = User.objects.exclude(username__endswith='@digiserve')
        updated_count = 0

        for user in users:
            user.username += '@digiserve'
            user.save()
            updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {updated_count} usernames."))
