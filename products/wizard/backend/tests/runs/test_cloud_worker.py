from types import SimpleNamespace
from uuid import uuid4

import pytest
from unittest.mock import MagicMock, patch

from products.tasks.backend.facade.repository import RepositoryPullRequest, SignedRepositoryCommit
from products.tasks.backend.facade.sandbox import SandboxNotFoundError
from products.wizard.backend.logic.cloud_worker import (
    GitRepositoryCloneRequest,
    GitRepositoryHandoffRequest,
    WizardExecutionRequest,
    WizardWorkerExecutionError,
    WizardWorkerProvisionRequest,
    WizardWorkerResult,
    WizardWorkerTimeoutError,
    clone_repository,
    create_git_repository_handoff,
    destroy_worker,
    execute_wizard,
    provision_worker,
)


def _execution_result(*, stdout: str = "", stderr: str = "", exit_code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, exit_code=exit_code)


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
@patch("products.wizard.backend.logic.cloud_worker.create_wizard_oauth_access_token_for_user")
@patch("products.wizard.backend.logic.cloud_worker.User.objects.get")
def test_provision_worker_configures_wizard_environment(
    get_user: MagicMock,
    create_wizard_token: MagicMock,
    get_sandbox_class: MagicMock,
) -> None:
    request = WizardWorkerProvisionRequest(team_id=7, created_by_id=13, run_id=uuid4())
    create_wizard_token.return_value = "wizard-secret"
    get_sandbox_class.return_value.create.return_value.id = "worker-id"

    sandbox_id = provision_worker(request)

    assert sandbox_id == "worker-id"
    get_user.assert_called_once_with(id=request.created_by_id)
    config = get_sandbox_class.return_value.create.call_args.args[0]
    assert "GITHUB_TOKEN" not in config.environment_variables
    assert config.environment_variables["POSTHOG_WIZARD_API_KEY"] == "wizard-secret"
    assert config.environment_variables["POSTHOG_WIZARD_RUN_ID"] == str(request.run_id)


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
@patch("products.wizard.backend.logic.cloud_worker.get_github_token")
def test_clone_repository_uses_integration_token(
    get_github_token: MagicMock,
    get_sandbox_class: MagicMock,
) -> None:
    request = GitRepositoryCloneRequest(
        sandbox_id="worker-id",
        github_integration_id=17,
        repository="PostHog/PostHog",
    )
    get_github_token.return_value = "github-secret"
    sandbox = get_sandbox_class.return_value.get_by_id.return_value
    sandbox.clone_repository.return_value = _execution_result()

    root_path = clone_repository(request)

    assert root_path == "/tmp/workspace/repos/posthog/posthog"
    get_sandbox_class.return_value.get_by_id.assert_called_once_with(request.sandbox_id)
    sandbox.clone_repository.assert_called_once_with(request.repository, github_token="github-secret", shallow=True)


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
@patch("products.wizard.backend.logic.cloud_worker.get_github_token", return_value="github-secret")
def test_clone_repository_rejects_clone_failure(
    _get_github_token: MagicMock,
    get_sandbox_class: MagicMock,
) -> None:
    request = GitRepositoryCloneRequest(
        sandbox_id="worker-id",
        github_integration_id=17,
        repository="PostHog/PostHog",
    )
    sandbox = get_sandbox_class.return_value.get_by_id.return_value
    sandbox.clone_repository.return_value = _execution_result(stderr="not found", exit_code=128)

    with pytest.raises(WizardWorkerExecutionError):
        clone_repository(request)


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
def test_execute_wizard_uses_prepared_workspace(get_sandbox_class: MagicMock) -> None:
    request = WizardExecutionRequest(
        sandbox_id="worker-id",
        workspace_path="/tmp/workspace/repos/posthog/posthog",
        team_id=7,
    )
    sandbox = get_sandbox_class.return_value.get_by_id.return_value
    sandbox.execute.return_value = _execution_result()

    execute_wizard(request)

    get_sandbox_class.return_value.get_by_id.assert_called_once_with(request.sandbox_id)
    command = sandbox.execute.call_args.args[0]
    assert command.startswith(f"cd {request.workspace_path} &&")
    assert "npx --yes @posthog/wizard@latest" in command
    assert "wizard-secret" not in command


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
def test_execute_wizard_maps_command_timeout(get_sandbox_class: MagicMock) -> None:
    request = WizardExecutionRequest(
        sandbox_id="worker-id",
        workspace_path="/tmp/workspace/repos/posthog/posthog",
        team_id=7,
    )
    get_sandbox_class.return_value.get_by_id.return_value.execute.return_value = _execution_result(exit_code=124)

    with pytest.raises(WizardWorkerTimeoutError):
        execute_wizard(request)


@patch("products.wizard.backend.logic.cloud_worker.repository_facade.create_pull_request")
@patch("products.wizard.backend.logic.cloud_worker.repository_facade.create_signed_commit")
@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
def test_git_repository_handoff_captures_diff_and_publishes_pull_request(
    get_sandbox_class: MagicMock,
    create_signed_commit: MagicMock,
    create_pull_request: MagicMock,
) -> None:
    request = GitRepositoryHandoffRequest(
        team_id=7,
        run_id=uuid4(),
        sandbox_id="worker-id",
        workspace_path="/tmp/workspace/repos/posthog/posthog",
        github_integration_id=17,
        repository="PostHog/PostHog",
    )
    sandbox = get_sandbox_class.return_value.get_by_id.return_value
    sandbox.execute.return_value = _execution_result(stdout="diff --git a/a b/a\n")
    branch = f"posthog/wizard-{request.run_id.hex[:12]}"
    create_signed_commit.return_value = SignedRepositoryCommit(
        repository=request.repository,
        branch=branch,
        commit_shas=("abc123",),
    )
    pull_request = RepositoryPullRequest(
        repository=request.repository,
        number=123,
        url="https://github.com/posthog/posthog/pull/123",
        head_branch=branch,
        base_branch="master",
    )
    create_pull_request.return_value = pull_request

    result = create_git_repository_handoff(request)

    assert result == WizardWorkerResult(diff=b"diff --git a/a b/a\n", pull_request=pull_request)
    assert "git add -N --all" in sandbox.execute.call_args.args[0]
    create_signed_commit.assert_called_once_with(
        sandbox,
        repository=request.repository,
        branch=branch,
        message="Set up PostHog",
    )
    create_pull_request.assert_called_once_with(
        team_id=request.team_id,
        integration_id=request.github_integration_id,
        repository=request.repository,
        head_branch=branch,
        title="Set up PostHog",
        body="This pull request contains changes created by Wizard, PostHog's setup agent.",
        source="wizard",
    )


@patch("products.wizard.backend.logic.cloud_worker.repository_facade.create_pull_request")
@patch("products.wizard.backend.logic.cloud_worker.repository_facade.create_signed_commit")
@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
def test_git_repository_handoff_skips_publish_without_changes(
    get_sandbox_class: MagicMock,
    create_signed_commit: MagicMock,
    create_pull_request: MagicMock,
) -> None:
    request = GitRepositoryHandoffRequest(
        team_id=7,
        run_id=uuid4(),
        sandbox_id="worker-id",
        workspace_path="/tmp/workspace/repos/posthog/posthog",
        github_integration_id=17,
        repository="PostHog/PostHog",
    )
    get_sandbox_class.return_value.get_by_id.return_value.execute.return_value = _execution_result()

    result = create_git_repository_handoff(request)

    assert result == WizardWorkerResult(diff=b"", pull_request=None)
    create_signed_commit.assert_not_called()
    create_pull_request.assert_not_called()


@patch("products.wizard.backend.logic.cloud_worker.get_sandbox_class")
def test_destroy_worker_accepts_already_destroyed_sandbox(get_sandbox_class: MagicMock) -> None:
    get_sandbox_class.return_value.get_by_id.side_effect = SandboxNotFoundError(
        "Worker not found.",
        {"sandbox_id": "worker-id"},
        RuntimeError("not found"),
    )

    destroy_worker("worker-id")
