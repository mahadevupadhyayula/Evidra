from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.text import get_valid_filename


def private_resume_storage() -> FileSystemStorage:
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)


def build_resume_storage_key(*, user_id: int, original_filename: str) -> str:
    safe_name = get_valid_filename(Path(original_filename).name) or "resume"
    return f"resumes/user-{user_id}/{uuid4().hex}-{safe_name}"
