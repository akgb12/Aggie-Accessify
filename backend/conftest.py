import os
from pathlib import Path

import boto3
import pytest
from django.conf import settings as django_settings
from django.core.files.storage import default_storage, storages
from django.test import Client
from django.utils.functional import empty
from moto import mock_aws

from accounts.models import User

os.environ["MODEL_PROVIDER"] = "fake"


@pytest.fixture(autouse=True)
def s3_storage(settings, tmp_path: Path):
    # Back every backend test with a fresh moto S3 bucket and scratch folder
    settings.SCRATCH_DIR = tmp_path / "scratch"
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket=django_settings.TEST_BUCKET_NAME
        )
        storages._storages = {}
        default_storage._wrapped = empty
        yield
    storages._storages = {}
    default_storage._wrapped = empty


@pytest.fixture
def user(db):
    # The signed-in account every API test acts as
    return User.objects.create_user(
        "tester", "correct-horse-battery", first_name="Test", last_name="User"
    )


@pytest.fixture
def client(user: User) -> Client:
    # Create a Django API test client that is already signed in
    signed_in = Client()
    signed_in.force_login(user)
    return signed_in
