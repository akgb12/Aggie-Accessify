from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from projects.models import Project


class Command(BaseCommand):
    help = "Give projects made before accounts existed to one user"

    def add_arguments(self, parser) -> None:
        parser.add_argument("username")

    def handle(self, *args, **options) -> None:
        username = options["username"].strip().lower()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as error:
            raise CommandError(
                f"No account named {username}. Register it in the app first."
            ) from error
        count = Project.objects.filter(owner__isnull=True).update(owner=user)
        self.stdout.write(f"Gave {count} project(s) to {username}.")
