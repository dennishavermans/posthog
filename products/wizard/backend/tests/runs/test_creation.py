import pytest

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.runs import CreateWizardRunInput, WizardRunStatus, WizardRunSurface


@pytest.mark.django_db
def test_create_run_starts_queued(team, user) -> None:
    run = wizard_facade.create_run(
        CreateWizardRunInput(
            team_id=team.id,
            created_by_id=user.id,
            surface=WizardRunSurface.CLOUD,
        )
    )

    assert run.team_id == team.id
    assert run.created_by_id == user.id
    assert run.surface == WizardRunSurface.CLOUD
    assert run.status == WizardRunStatus.QUEUED
    assert run.outcome is None
    assert run.error_code is None
