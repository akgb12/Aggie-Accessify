import json

import pytest
from django.core.cache import cache
from django.test import Client

from accounts.models import User
from projects.models import Project, Run

GOOD_PASSWORD = "maroon-and-white-2026"


@pytest.fixture(autouse=True)
def clear_throttle():
    # Failed-login counters live in the cache and must not leak between tests
    cache.clear()


def _post(client: Client, path: str, body: dict[str, object]):
    return client.post(path, data=json.dumps(body), content_type="application/json")


def _register_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "username": "jdoe",
        "first_name": "Jane",
        "last_name": "Doe",
        "password": GOOD_PASSWORD,
        "confirm_password": GOOD_PASSWORD,
    }
    body.update(overrides)
    return body


@pytest.mark.django_db
def test_register_creates_a_signed_in_account() -> None:
    anonymous = Client()
    response = _post(anonymous, "/api/auth/register", _register_body(username="JDoe"))
    assert response.status_code == 201
    assert response.json()["username"] == "jdoe"
    assert response.json()["preferences"] == {
        "default_effort": "medium",
        "show_demo_options": False,
    }
    assert anonymous.get("/api/auth/me").json()["first_name"] == "Jane"
    assert User.objects.get(username="jdoe").password != GOOD_PASSWORD


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"confirm_password": "something-else-entirely"}, "do not match"),
        ({"password": "short1", "confirm_password": "short1"}, "at least 10"),
        ({"password": "password123", "confirm_password": "password123"}, "common"),
        ({"username": "j"}, "TAMU username"),
        ({"username": "has space"}, "TAMU username"),
        ({"first_name": "   "}, "first and last name"),
    ],
)
def test_register_rejects_bad_input(overrides: dict[str, object], fragment: str) -> None:
    response = _post(Client(), "/api/auth/register", _register_body(**overrides))
    assert response.status_code == 400
    assert fragment in response.json()["detail"]
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_register_refuses_a_taken_username_in_any_case() -> None:
    _post(Client(), "/api/auth/register", _register_body())
    response = _post(Client(), "/api/auth/register", _register_body(username="JDOE"))
    assert response.status_code == 409


@pytest.mark.django_db
def test_login_and_logout() -> None:
    _post(Client(), "/api/auth/register", _register_body())
    client = Client()
    assert (
        _post(client, "/api/auth/login", {"username": "jdoe", "password": "nope"}).status_code
        == 400
    )
    assert client.get("/api/auth/me").status_code == 401
    assert (
        _post(
            client, "/api/auth/login", {"username": "JDoe", "password": GOOD_PASSWORD}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.django_db
def test_repeated_failures_lock_the_username_for_a_while() -> None:
    _post(Client(), "/api/auth/register", _register_body())
    client = Client()
    for _ in range(5):
        _post(client, "/api/auth/login", {"username": "jdoe", "password": "wrong"})
    locked = _post(client, "/api/auth/login", {"username": "jdoe", "password": GOOD_PASSWORD})
    assert locked.status_code == 429


@pytest.mark.django_db
def test_every_data_endpoint_needs_a_session() -> None:
    anonymous = Client()
    for method, path in [
        ("get", "/api/projects"),
        ("post", "/api/projects"),
        ("get", "/api/projects/00000000-0000-0000-0000-000000000000"),
        ("get", "/api/runs/00000000-0000-0000-0000-000000000000"),
        ("get", "/api/runs/00000000-0000-0000-0000-000000000000/artifact/report.html"),
        ("get", "/api/auth/usage"),
        ("delete", "/api/auth/projects"),
    ]:
        assert getattr(anonymous, method)(path).status_code == 401, path


@pytest.mark.django_db
def test_users_cannot_see_or_change_each_others_projects(client: Client) -> None:
    created = _post(client, "/api/projects", {"name": "Mine"}).json()
    other = User.objects.create_user("other", GOOD_PASSWORD, first_name="O", last_name="U")
    stranger = Client()
    stranger.force_login(other)
    assert stranger.get("/api/projects").json() == []
    assert stranger.get(f"/api/projects/{created['id']}").status_code == 404
    assert stranger.delete(f"/api/projects/{created['id']}").status_code == 404
    assert (
        stranger.patch(
            f"/api/projects/{created['id']}",
            data=json.dumps({"name": "Stolen"}),
            content_type="application/json",
        ).status_code
        == 404
    )
    run = Run.objects.create(
        project=Project.objects.get(id=created["id"]), effort="low", model_provider="fake"
    )
    assert stranger.get(f"/api/runs/{run.id}").status_code == 404
    assert stranger.get(f"/api/runs/{run.id}/artifact/report.html").status_code == 404
    assert client.get(f"/api/runs/{run.id}").status_code == 200


@pytest.mark.django_db
def test_preferences_and_name_are_saved(client: Client) -> None:
    response = client.patch(
        "/api/auth/me",
        data=json.dumps(
            {
                "first_name": "Tess",
                "preferences": {"default_effort": "high", "show_demo_options": True},
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["first_name"] == "Tess"
    assert client.get("/api/auth/me").json()["preferences"]["default_effort"] == "high"
    bad = client.patch(
        "/api/auth/me",
        data=json.dumps({"preferences": {"default_effort": "baseline"}}),
        content_type="application/json",
    )
    assert bad.status_code == 422


@pytest.mark.django_db
def test_change_password_keeps_the_session_and_checks_the_old_one(
    client: Client, user: User
) -> None:
    body = {
        "current_password": "wrong",
        "new_password": "a-brand-new-passphrase",
        "confirm_password": "a-brand-new-passphrase",
    }
    assert _post(client, "/api/auth/password", body).status_code == 400
    body["current_password"] = "correct-horse-battery"
    assert _post(client, "/api/auth/password", body).status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    user.refresh_from_db()
    assert user.check_password("a-brand-new-passphrase")


@pytest.mark.django_db
def test_delete_all_projects_leaves_other_accounts_alone(client: Client) -> None:
    _post(client, "/api/projects", {"name": "A"})
    _post(client, "/api/projects", {"name": "B"})
    other = User.objects.create_user("other", GOOD_PASSWORD, first_name="O", last_name="U")
    Project.objects.create(owner=other, name="Theirs")
    response = client.delete("/api/auth/projects")
    assert response.json()["detail"] == "Deleted 2 projects."
    assert client.get("/api/projects").json() == []
    assert Project.objects.filter(owner=other).count() == 1


@pytest.mark.django_db
def test_delete_account_needs_the_password_and_removes_everything(
    client: Client, user: User
) -> None:
    _post(client, "/api/projects", {"name": "A"})
    assert _post(client, "/api/auth/delete", {"password": "wrong"}).status_code == 400
    assert User.objects.filter(id=user.id).exists()
    assert (
        _post(client, "/api/auth/delete", {"password": "correct-horse-battery"}).status_code == 200
    )
    assert not User.objects.filter(id=user.id).exists()
    assert Project.objects.count() == 0
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.django_db
def test_usage_adds_up_only_this_accounts_runs(client: Client, user: User) -> None:
    project = Project.objects.create(owner=user, name="P")
    Run.objects.create(
        project=project,
        effort="low",
        model_provider="fake",
        status=Run.Status.SUCCEEDED,
        input_tokens=100,
        output_tokens=50,
        cost_usd="0.25",
    )
    other = User.objects.create_user("other", GOOD_PASSWORD, first_name="O", last_name="U")
    Run.objects.create(
        project=Project.objects.create(owner=other, name="Q"),
        effort="low",
        model_provider="fake",
        cost_usd="9",
    )
    usage = client.get("/api/auth/usage").json()
    assert usage["projects"] == 1
    assert usage["runs"] == 1
    assert usage["succeeded_runs"] == 1
    assert usage["input_tokens"] == 100
    assert usage["cost_usd"] == 0.25
    assert usage["cost_usd_this_month"] == 0.25


@pytest.mark.django_db
def test_writes_need_the_csrf_token_when_signed_in(user: User) -> None:
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    assert strict.post("/api/auth/logout").status_code == 200  # no session auth on logout
    strict.force_login(user)
    refused = strict.post(
        "/api/projects", data=json.dumps({"name": "X"}), content_type="application/json"
    )
    assert refused.status_code == 403
    strict.get("/api/auth/csrf")
    token = strict.cookies["csrftoken"].value
    allowed = strict.post(
        "/api/projects",
        data=json.dumps({"name": "X"}),
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert allowed.status_code == 201
