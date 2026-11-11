from datetime import datetime
from typing import Literal

from ninja import Schema
from pydantic import Field


class PreferencesSchema(Schema):
    default_effort: Literal["low", "medium", "high"] = "medium"
    show_demo_options: bool = False


class UserSchema(Schema):
    id: int
    username: str
    first_name: str
    last_name: str
    preferences: PreferencesSchema
    created_at: datetime


class RegisterSchema(Schema):
    username: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class LoginSchema(Schema):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ProfileUpdateSchema(Schema):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    preferences: PreferencesSchema | None = None


class PasswordChangeSchema(Schema):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class PasswordConfirmSchema(Schema):
    password: str = Field(min_length=1, max_length=256)


class UsageSchema(Schema):
    projects: int
    runs: int
    succeeded_runs: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cost_usd_this_month: float
    # The account's hard limit on model spend, what it has spent in total (runs in deleted
    # projects included), and what is left once running runs are allowed for
    limit_usd: float
    spent_usd: float
    remaining_usd: float


class MessageSchema(Schema):
    detail: str
