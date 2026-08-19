from types import SimpleNamespace
from uuid import uuid4

import pytest
from unittest.mock import MagicMock, patch

from products.wizard.backend.logic.cloud_worker import (
    WizardWorkerExecutionError,
    WizardWorkerInput,
    WizardWorkerTimeoutError,
    execute_wizard_worker,
)


def _execution_result(*, stdout: str = "", stderr: str = "", exit_code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, exit_code=exit_code)


def _input() -> WizardWorkerInput:
    return WizardWorkerInput(
        team_id=7,
        created_by_id=13,
        run_id=uuid4(),
        github_integration_id=17,
        repository="PostHog/PostHog",
    )


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
@patch("products.wizard.backend.logic.cloud_worker.create_wizard_oauth_access_token_for_user")
@patch("products.wizard.backend.logic.cloud_worker.get_github_token")
@patch("products.wizard.backend.logic.cloud_worker.User.objects.get")
def test_execute_wizard_worker_returns_git_diff_and_cleans_up(
    get_user: MagicMock,
    get_github_token: MagicMock,
    create_wizard_token: MagicMock,
    get_sandbox_class: MagicMock,
) -> None:
    input = _input()
    get_github_token.return_value = "github-secret"
    create_wizard_token.return_value = "wizard-secret"
    sandbox = MagicMock()
    sandbox.clone_repository.return_value = _execution_result()
    sandbox.execute.side_effect = [_execution_result(), _execution_result(stdout="diff --git a/a b/a\n")]
    get_sandbox_class.return_value.create.return_value = sandbox

    result = execute_wizard_worker(input)

    assert result == b"diff --git a/a b/a\n"
    get_user.assert_called_once_with(id=input.created_by_id)
    sandbox.clone_repository.assert_called_once_with(input.repository, github_token="github-secret", shallow=True)
    sandbox.destroy.assert_called_once_with()
    config = get_sandbox_class.return_value.create.call_args.args[0]
    assert config.environment_variables["POSTHOG_WIZARD_API_KEY"] == "wizard-secret"
    assert config.environment_variables["POSTHOG_WIZARD_RUN_ID"] == str(input.run_id)
    assert "wizard-secret" not in sandbox.execute.call_args_list[0].args[0]
    assert "git add -N --all" in sandbox.execute.call_args_list[1].args[0]


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
@patch("products.wizard.backend.logic.cloud_worker.create_wizard_oauth_access_token_for_user", return_value="token")
@patch("products.wizard.backend.logic.cloud_worker.get_github_token", return_value="github-token")
@patch("products.wizard.backend.logic.cloud_worker.User.objects.get")
def test_execute_wizard_worker_maps_timeout_and_cleans_up(
    _get_user: MagicMock,
    _get_github_token: MagicMock,
    _create_wizard_token: MagicMock,
    get_sandbox_class: MagicMock,
) -> None:
    sandbox = MagicMock()
    sandbox.clone_repository.return_value = _execution_result()
    sandbox.execute.return_value = _execution_result(exit_code=124)
    get_sandbox_class.return_value.create.return_value = sandbox

    with pytest.raises(WizardWorkerTimeoutError):
        execute_wizard_worker(_input())

    sandbox.destroy.assert_called_once_with()


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
@patch("products.wizard.backend.logic.cloud_worker.create_wizard_oauth_access_token_for_user", return_value="token")
@patch("products.wizard.backend.logic.cloud_worker.get_github_token", return_value="github-token")
@patch("products.wizard.backend.logic.cloud_worker.User.objects.get")
def test_execute_wizard_worker_rejects_clone_failure(
    _get_user: MagicMock,
    _get_github_token: MagicMock,
    _create_wizard_token: MagicMock,
    get_sandbox_class: MagicMock,
) -> None:
    sandbox = MagicMock()
    sandbox.clone_repository.return_value = _execution_result(stderr="not found", exit_code=128)
    get_sandbox_class.return_value.create.return_value = sandbox

    with pytest.raises(WizardWorkerExecutionError):
        execute_wizard_worker(_input())

    sandbox.execute.assert_not_called()
    sandbox.destroy.assert_called_once_with()
