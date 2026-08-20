from types import SimpleNamespace
from uuid import uuid4

import pytest
from unittest.mock import MagicMock, patch

from products.tasks.backend.facade.repository import RepositoryPullRequest, SignedRepositoryCommit
from products.wizard.backend.logic.cloud_worker import (
    WizardWorkerExecutionError,
    WizardWorkerInput,
    WizardWorkerResult,
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


@patch("products.wizard.backend.logic.cloud_worker.repository_facade.create_pull_request")
@patch("products.wizard.backend.logic.cloud_worker.repository_facade.create_signed_commit")
@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
@patch("products.wizard.backend.logic.cloud_worker.create_wizard_oauth_access_token_for_user")
@patch("products.wizard.backend.logic.cloud_worker.get_github_token")
@patch("products.wizard.backend.logic.cloud_worker.User.objects.get")
def test_execute_wizard_worker_publishes_pull_request_and_cleans_up(
    get_user: MagicMock,
    get_github_token: MagicMock,
    create_wizard_token: MagicMock,
    get_sandbox_class: MagicMock,
    create_signed_commit: MagicMock,
    create_pull_request: MagicMock,
) -> None:
    input = _input()
    get_github_token.return_value = "github-secret"
    create_wizard_token.return_value = "wizard-secret"
    pull_request = RepositoryPullRequest(
        repository=input.repository,
        number=123,
        url="https://github.com/posthog/posthog/pull/123",
        head_branch=f"posthog/wizard-{input.run_id.hex[:12]}",
        base_branch="master",
    )
    create_signed_commit.return_value = SignedRepositoryCommit(
        repository=input.repository,
        branch=pull_request.head_branch,
        commit_shas=("abc123",),
    )
    create_pull_request.return_value = pull_request
    sandbox = MagicMock()
    sandbox.clone_repository.return_value = _execution_result()
    sandbox.execute.side_effect = [_execution_result(), _execution_result(stdout="diff --git a/a b/a\n")]
    get_sandbox_class.return_value.create.return_value = sandbox

    result = execute_wizard_worker(input)

    assert result == WizardWorkerResult(diff=b"diff --git a/a b/a\n", pull_request=pull_request)
    get_user.assert_called_once_with(id=input.created_by_id)
    sandbox.clone_repository.assert_called_once_with(input.repository, github_token="github-secret", shallow=True)
    sandbox.destroy.assert_called_once_with()
    config = get_sandbox_class.return_value.create.call_args.args[0]
    assert "GITHUB_TOKEN" not in config.environment_variables
    assert config.environment_variables["POSTHOG_WIZARD_API_KEY"] == "wizard-secret"
    assert config.environment_variables["POSTHOG_WIZARD_RUN_ID"] == str(input.run_id)
    assert "wizard-secret" not in sandbox.execute.call_args_list[0].args[0]
    assert "git add -N --all" in sandbox.execute.call_args_list[1].args[0]
    create_signed_commit.assert_called_once_with(
        sandbox,
        repository=input.repository,
        branch=pull_request.head_branch,
        message="Set up PostHog",
    )
    create_pull_request.assert_called_once_with(
        team_id=input.team_id,
        integration_id=input.github_integration_id,
        repository=input.repository,
        head_branch=pull_request.head_branch,
        title="Set up PostHog",
        body="This pull request contains changes created by Wizard, PostHog's setup agent.",
        source="wizard",
    )


@patch("products.wizard.backend.logic.cloud_worker.repository_facade.create_pull_request")
@patch("products.wizard.backend.logic.cloud_worker.repository_facade.create_signed_commit")
@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
@patch("products.wizard.backend.logic.cloud_worker.create_wizard_oauth_access_token_for_user", return_value="token")
@patch("products.wizard.backend.logic.cloud_worker.get_github_token", return_value="github-token")
@patch("products.wizard.backend.logic.cloud_worker.User.objects.get")
def test_execute_wizard_worker_does_not_publish_without_changes(
    _get_user: MagicMock,
    _get_github_token: MagicMock,
    _create_wizard_token: MagicMock,
    get_sandbox_class: MagicMock,
    create_signed_commit: MagicMock,
    create_pull_request: MagicMock,
) -> None:
    sandbox = MagicMock()
    sandbox.clone_repository.return_value = _execution_result()
    sandbox.execute.side_effect = [_execution_result(), _execution_result()]
    get_sandbox_class.return_value.create.return_value = sandbox

    result = execute_wizard_worker(_input())

    assert result == WizardWorkerResult(diff=b"", pull_request=None)
    create_signed_commit.assert_not_called()
    create_pull_request.assert_not_called()
    sandbox.destroy.assert_called_once_with()


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
