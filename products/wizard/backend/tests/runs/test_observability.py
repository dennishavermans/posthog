import pytest
from unittest.mock import patch

from products.wizard.backend.facade.contracts import CreateWizardRunInput, LocalFolderWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunStatus
from products.wizard.backend.logic.runs import lifecycle
from products.wizard.backend.observability import service
from products.wizard.backend.observability.service import terminal_event_name


@pytest.mark.django_db
def test_run_creation_emits_observability(team, user) -> None:
    with patch("products.wizard.backend.logic.runs.lifecycle.run_observability") as observability:
        run = lifecycle.create_run(
            CreateWizardRunInput(
                team_id=team.id,
                created_by_id=user.id,
                environment=WizardRunEnvironment.LOCAL,
                workspace=LocalFolderWorkspace(project_name="example"),
                program_id="posthog-integration",
            )
        )

    observability.run_created.assert_called_once_with(run)


@pytest.mark.django_db
def test_run_transition_emits_observability(team, user) -> None:
    run = lifecycle.create_run(
        CreateWizardRunInput(
            team_id=team.id,
            created_by_id=user.id,
            environment=WizardRunEnvironment.LOCAL,
            workspace=LocalFolderWorkspace(project_name="example"),
            program_id="posthog-integration",
        )
    )

    with patch("products.wizard.backend.logic.runs.lifecycle.run_observability") as observability:
        completed = lifecycle.complete_run(team.id, run.id)

    observability.run_transitioned.assert_called_once_with(run, completed)


def test_observability_failures_do_not_escape() -> None:
    with (
        patch.object(service, "report_run_created", side_effect=RuntimeError),
        patch.object(service, "enqueue_run_event", side_effect=RuntimeError),
    ):
        service.run_created(object())


def test_terminal_event_name_matches_status() -> None:
    assert terminal_event_name(WizardRunStatus.COMPLETED) == "wizard run completed"
    assert terminal_event_name(WizardRunStatus.FAILED) == "wizard run failed"
    assert terminal_event_name(WizardRunStatus.CANCELLED) == "wizard run cancelled"
