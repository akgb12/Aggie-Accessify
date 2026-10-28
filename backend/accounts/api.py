import re
from typing import Any

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.middleware.csrf import get_token
from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError
from ninja.security import SessionAuth

from accounts.models import DEFAULT_PREFERENCES, User
from accounts.schemas import (
    LoginSchema,
    MessageSchema,
    PasswordChangeSchema,
    PasswordConfirmSchema,
    ProfileUpdateSchema,
    RegisterSchema,
    UsageSchema,
    UserSchema,
)
from projects.models import Project, Run
from projects.services import delete_project_completely

router = Router(tags=["accounts"])
session_auth = SessionAuth()

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 15 * 60


def _user_payload(user: User) -> dict[str, Any]:
    # Merge stored preferences over the defaults so new options appear for old accounts
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "preferences": {**DEFAULT_PREFERENCES, **user.preferences},
        "created_at": user.created_at,
    }


def _password_problem(password: str, confirm: str, user: User | None = None) -> str | None:
    # Check the confirmation and Django's password rules; return a readable problem or None
    if password != confirm:
        return "The two passwords do not match."
    try:
        validate_password(password, user)
    except ValidationError as error:
        return " ".join(error.messages)
    return None


def _throttle_key(username: str) -> str:
    return f"login-failures:{username}"


@router.get("/csrf", auth=None, response=MessageSchema)
def csrf(request):
    # Hand the browser a CSRF cookie before it signs in or registers
    get_token(request)
    return {"detail": "ok"}


@router.post(
    "/register", auth=None, response={201: UserSchema, 400: MessageSchema, 409: MessageSchema}
)
def register(request, payload: RegisterSchema):
    # Create an account and sign it in
    username = payload.username.strip().lower()
    if not USERNAME_PATTERN.match(username):
        raise HttpError(
            400,
            "Use your TAMU username: 3 to 32 letters or numbers "
            "(dots, dashes and underscores allowed).",
        )
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    if not first_name or not last_name:
        raise HttpError(400, "Enter your first and last name.")
    candidate = User(username=username, first_name=first_name, last_name=last_name)
    problem = _password_problem(payload.password, payload.confirm_password, candidate)
    if problem:
        raise HttpError(400, problem)
    if User.objects.filter(username=username).exists():
        raise HttpError(409, "That username already has an account. Sign in instead.")
    user = User.objects.create_user(
        username, payload.password, first_name=first_name, last_name=last_name
    )
    login(request, user)
    return Status(201, _user_payload(user))


@router.post(
    "/login", auth=None, response={200: UserSchema, 400: MessageSchema, 429: MessageSchema}
)
def sign_in(request, payload: LoginSchema):
    # Sign in with a username and password; repeated failures lock the username briefly
    username = payload.username.strip().lower()
    key = _throttle_key(username)
    if cache.get(key, 0) >= MAX_FAILED_LOGINS:
        raise HttpError(429, "Too many failed attempts. Try again in a few minutes.")
    user = authenticate(request, username=username, password=payload.password)
    if user is None:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, LOCKOUT_SECONDS)
        raise HttpError(400, "Incorrect username or password.")
    cache.delete(key)
    login(request, user)
    return _user_payload(user)


@router.post("/logout", auth=None, response=MessageSchema)
def sign_out(request):
    # End the session; fine to call when already signed out
    logout(request)
    return {"detail": "Signed out."}


@router.get("/me", auth=session_auth, response=UserSchema)
def me(request):
    # Return the signed-in user
    return _user_payload(request.user)


@router.patch("/me", auth=session_auth, response=UserSchema)
def update_me(request, payload: ProfileUpdateSchema):
    # Update name and preferences
    user: User = request.user
    if payload.first_name is not None:
        user.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        user.last_name = payload.last_name.strip()
    if not user.first_name or not user.last_name:
        raise HttpError(400, "Name cannot be blank.")
    if payload.preferences is not None:
        user.preferences = {**DEFAULT_PREFERENCES, **payload.preferences.model_dump()}
    user.save(update_fields=["first_name", "last_name", "preferences"])
    return _user_payload(user)


@router.post("/password", auth=session_auth, response={200: MessageSchema, 400: MessageSchema})
def change_password(request, payload: PasswordChangeSchema):
    # Change the password and keep this browser signed in
    user: User = request.user
    if not user.check_password(payload.current_password):
        raise HttpError(400, "Current password is incorrect.")
    problem = _password_problem(payload.new_password, payload.confirm_password, user)
    if problem:
        raise HttpError(400, problem)
    user.set_password(payload.new_password)
    user.save(update_fields=["password"])
    update_session_auth_hash(request, user)
    return {"detail": "Password updated."}


@router.get("/usage", auth=session_auth, response=UsageSchema)
def usage(request):
    # Summarize this account's runs and model spend
    runs = Run.objects.filter(project__owner=request.user)
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    totals = runs.aggregate(
        input=Sum("input_tokens"), output=Sum("output_tokens"), cost=Sum("cost_usd")
    )
    month = runs.filter(created_at__gte=month_start).aggregate(cost=Sum("cost_usd"))
    return {
        "projects": Project.objects.filter(owner=request.user).count(),
        "runs": runs.count(),
        "succeeded_runs": runs.filter(status=Run.Status.SUCCEEDED).count(),
        "input_tokens": totals["input"] or 0,
        "output_tokens": totals["output"] or 0,
        "cost_usd": float(totals["cost"] or 0),
        "cost_usd_this_month": float(month["cost"] or 0),
    }


def _delete_projects(user: User) -> int:
    # Delete every project this user owns along with its stored files
    count = 0
    for project in Project.objects.filter(owner=user).prefetch_related("files", "runs"):
        delete_project_completely(project)
        count += 1
    return count


@router.delete("/projects", auth=session_auth, response={200: MessageSchema})
def delete_all_projects(request):
    # Data controls: remove all of this account's projects
    count = _delete_projects(request.user)
    return {"detail": f"Deleted {count} {'project' if count == 1 else 'projects'}."}


@router.post("/delete", auth=session_auth, response={200: MessageSchema, 400: MessageSchema})
def delete_account(request, payload: PasswordConfirmSchema):
    # Permanently delete the account, its projects and its stored files
    user: User = request.user
    if not user.check_password(payload.password):
        raise HttpError(400, "Password is incorrect.")
    _delete_projects(user)
    logout(request)
    user.delete()
    return {"detail": "Account deleted."}
