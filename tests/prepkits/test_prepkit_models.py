import pytest
from django.db import IntegrityError

from apps.prepkits.models import PrepKit, PrepKitStatus
from tests.prepkits.helpers import make_paid_sprint


@pytest.mark.django_db
def test_prepkit_defaults_to_pending():
    _user, sprint = make_paid_sprint()

    prepkit = PrepKit.objects.create(sprint=sprint, input_revision="rev")

    assert prepkit.status == PrepKitStatus.PENDING


@pytest.mark.django_db
def test_one_current_prepkit_per_revision():
    _user, sprint = make_paid_sprint()
    PrepKit.objects.create(sprint=sprint, input_revision="rev", status=PrepKitStatus.PENDING)

    with pytest.raises(IntegrityError):
        PrepKit.objects.create(sprint=sprint, input_revision="rev", status=PrepKitStatus.READY)


@pytest.mark.django_db
def test_failed_prepkit_does_not_block_retry_record():
    _user, sprint = make_paid_sprint()
    PrepKit.objects.create(sprint=sprint, input_revision="rev", status=PrepKitStatus.FAILED)

    retry = PrepKit.objects.create(
        sprint=sprint, input_revision="rev", status=PrepKitStatus.PENDING
    )

    assert retry.status == PrepKitStatus.PENDING
