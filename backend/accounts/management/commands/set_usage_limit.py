from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Set how much one account may spend on model calls in total, in US dollars"

    def add_arguments(self, parser) -> None:
        parser.add_argument("username")
        parser.add_argument("dollars")

    def handle(self, *args, **options) -> None:
        username = options["username"].strip().lower()
        try:
            limit = Decimal(options["dollars"]).quantize(Decimal("0.01"))
        except InvalidOperation as error:
            raise CommandError("Give the limit in dollars, such as 20 or 35.50.") from error
        if limit < 0:
            raise CommandError("The limit cannot be negative.")
        updated = User.objects.filter(username=username).update(usage_limit_usd=limit)
        if not updated:
            raise CommandError(f"No account named {username}.")
        self.stdout.write(f"{username} may now spend ${limit} in total.")
