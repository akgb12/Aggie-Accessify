from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from accounts.models import User
from projects.models import Run

# A running run holds back what it may spend, so runs at the same time cannot pass the limit
# together. A run still marked running after this long was cut off and holds nothing back.
RESERVATION_HOURS = 2


def reserved_usd(user: User) -> Decimal:
    # What this account's running runs may still spend
    since = timezone.now() - timedelta(hours=RESERVATION_HOURS)
    running = Run.objects.filter(
        project__owner=user, status=Run.Status.RUNNING, started_at__gte=since
    )
    return running.aggregate(total=Sum("budget_usd"))["total"] or Decimal(0)


def remaining_usd(user: User) -> Decimal:
    # What this account can still spend before its hard limit
    left = user.usage_limit_usd - user.spent_usd - reserved_usd(user)
    return max(Decimal(0), left)


def limit_message(user: User) -> str:
    return (
        f"This account has used its ${user.usage_limit_usd:.2f} lifetime usage limit, so no "
        "more runs can start. Earlier results can still be viewed and downloaded."
    )


def reserve_run_budget(run: Run, effort_cap: Decimal) -> Decimal | None:
    # Give a starting run as much of its owner's remaining limit as its effort allows and mark
    # it running. None when the project has no owner, so there is no limit to apply.
    owner_id = run.project.owner_id
    with transaction.atomic():
        if owner_id is None:
            granted = None
        else:
            # Locking the account makes runs that start together take turns here
            owner = User.objects.select_for_update().get(pk=owner_id)
            granted = min(effort_cap, remaining_usd(owner))
            run.budget_usd = granted
        run.status = Run.Status.RUNNING
        run.started_at = timezone.now()
        run.error_message = ""
        run.save(update_fields=["status", "started_at", "error_message", "budget_usd"])
    return granted


def charge_run(run: Run) -> None:
    # Add what a finished run cost to its owner's spend
    if run.project.owner_id is None or run.cost_usd <= 0:
        return
    User.objects.filter(pk=run.project.owner_id).update(spent_usd=F("spent_usd") + run.cost_usd)
