import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone

from accounts.models import User
from accounts.usage import charge_run, remaining_usd, reserve_run_budget
from projects import tasks
from projects.models import Project, Run


def _run(user: User, **fields: object) -> Run:
    project = Project.objects.create(owner=user, name="Lecture")
    return Run.objects.create(project=project, effort="high", model_provider="fake", **fields)


@pytest.mark.django_db
def test_every_account_starts_with_a_twenty_dollar_limit(client: Client, user: User) -> None:
    usage = client.get("/api/auth/usage").json()
    assert usage["limit_usd"] == 20.0
    assert usage["spent_usd"] == 0.0
    assert usage["remaining_usd"] == 20.0


@pytest.mark.django_db
def test_spend_survives_deleting_the_project(client: Client, user: User) -> None:
    run = _run(user, cost_usd=Decimal("1.25"), status=Run.Status.SUCCEEDED)
    charge_run(run)
    run.project.delete()
    usage = client.get("/api/auth/usage").json()
    assert usage["spent_usd"] == 1.25
    assert usage["remaining_usd"] == 18.75
    assert usage["cost_usd"] == 0.0


@pytest.mark.django_db
def test_no_run_starts_once_the_limit_is_reached(client: Client, user: User) -> None:
    User.objects.filter(pk=user.pk).update(spent_usd=Decimal("20"))
    project = Project.objects.create(owner=user, name="Lecture")
    for path in (f"/api/projects/{project.id}/runs", f"/api/projects/{project.id}/runs/all"):
        response = client.post(
            path, data=json.dumps({"effort": "low"}), content_type="application/json"
        )
        assert response.status_code == 403
        assert "$20.00 lifetime usage limit" in response.json()["detail"]
    assert not Run.objects.exists()


@pytest.mark.django_db
def test_a_starting_run_gets_only_what_is_left(user: User) -> None:
    User.objects.filter(pk=user.pk).update(spent_usd=Decimal("19.40"))
    run = _run(user)
    granted = reserve_run_budget(run, Decimal("3.00"))
    assert granted == Decimal("0.60")
    run.refresh_from_db()
    assert run.status == Run.Status.RUNNING
    # While it runs, what it may spend is held back from every other run
    user.refresh_from_db()
    assert remaining_usd(user) == 0
    second = _run(user)
    assert reserve_run_budget(second, Decimal("3.00")) == 0


@pytest.mark.django_db
def test_a_run_left_running_long_ago_holds_nothing_back(user: User) -> None:
    _run(
        user,
        status=Run.Status.RUNNING,
        budget_usd=Decimal("3"),
        started_at=timezone.now() - timedelta(hours=5),
    )
    assert remaining_usd(user) == Decimal("20")


@pytest.mark.django_db
def test_the_worker_refuses_a_queued_run_after_the_limit(user: User) -> None:
    run = _run(user)
    User.objects.filter(pk=user.pk).update(spent_usd=Decimal("20"))
    tasks.run_pipeline_task.call(str(run.id))
    run.refresh_from_db()
    assert run.status == Run.Status.FAILED
    assert run.stop_reason == "usage_limit"
    assert "usage limit" in run.error_message


@pytest.mark.django_db
def test_a_run_that_fails_partway_still_pays_for_its_calls(user: User, monkeypatch) -> None:
    class Billed(RuntimeError):
        cost_usd = 0.4

    class Client:
        def complete_structured(self, request):
            raise Billed("schema mismatch")

    def failing_run(bundle, client, settings, **options):
        assert options["max_cost_usd"] == 3.0
        with pytest.raises(Billed):
            client.complete_structured(None)
        raise RuntimeError("compile failed")

    monkeypatch.setattr(tasks, "_model_client", lambda settings, fresh: Client())
    monkeypatch.setattr(tasks, "materialize_project", lambda project, root: None)
    monkeypatch.setattr(tasks, "run_to_folder", failing_run)
    run = _run(user)
    with pytest.raises(RuntimeError):
        tasks.run_pipeline_task.call(str(run.id))
    run.refresh_from_db()
    user.refresh_from_db()
    assert run.status == Run.Status.FAILED
    assert run.cost_usd == Decimal("0.4")
    assert user.spent_usd == Decimal("0.4")


@pytest.mark.django_db
def test_the_limit_can_be_raised_for_one_account(user: User) -> None:
    call_command("set_usage_limit", "Tester", "35.5")
    user.refresh_from_db()
    assert user.usage_limit_usd == Decimal("35.50")
    with pytest.raises(CommandError):
        call_command("set_usage_limit", "nobody", "10")
    with pytest.raises(CommandError):
        call_command("set_usage_limit", "tester", "-1")
