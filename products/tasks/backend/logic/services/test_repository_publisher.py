import json
from types import SimpleNamespace

from unittest.mock import MagicMock, patch

from products.tasks.backend.facade.repository import create_pull_request, create_signed_commit


def _execution_result(*, stdout: str = "", stderr: str = "", exit_code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, exit_code=exit_code)


def test_create_signed_commit_publishes_staged_checkout() -> None:
    sandbox = MagicMock()
    sandbox.execute.side_effect = [
        _execution_result(),
        _execution_result(
            stdout=json.dumps(
                {
                    "branch": "posthog/wizard-123",
                    "repository": "posthog/posthog",
                    "commits": [{"sha": "abc123", "url": "https://github.com/posthog/posthog/commit/abc123"}],
                }
            )
        ),
    ]

    result = create_signed_commit(
        sandbox,
        repository="posthog/posthog",
        branch="posthog/wizard-123",
        message="Set up PostHog",
    )

    assert result.repository == "posthog/posthog"
    assert result.branch == "posthog/wizard-123"
    assert result.commit_shas == ("abc123",)
    assert "git add --all" in sandbox.execute.call_args_list[0].args[0]
    assert "@posthog/git/signed-commit" in sandbox.execute.call_args_list[1].args[0]


@patch("products.tasks.backend.logic.services.repository_publisher.GitHubIntegration")
@patch("products.tasks.backend.logic.services.repository_publisher.Integration.objects.filter")
def test_create_pull_request_opens_repository_default_branch(
    filter_integrations: MagicMock,
    github_integration_class: MagicMock,
) -> None:
    integration = MagicMock()
    filter_integrations.return_value.first.return_value = integration
    github = github_integration_class.return_value
    github.organization.return_value = "posthog"
    github.get_default_branch.return_value = "master"
    github.list_pull_requests.return_value = {"success": True, "pull_requests": []}
    github.create_pull_request.return_value = {
        "success": True,
        "pr_number": 123,
        "pr_url": "https://github.com/posthog/posthog/pull/123",
    }

    result = create_pull_request(
        team_id=7,
        integration_id=13,
        repository="posthog/posthog",
        head_branch="posthog/wizard-123",
        title="Set up PostHog",
        body="Created by the setup agent.",
        source="wizard",
    )

    filter_integrations.assert_called_once_with(team_id=7, id=13, kind="github")
    github.create_pull_request.assert_called_once_with(
        "posthog",
        "Set up PostHog",
        "Created by the setup agent.",
        "posthog/wizard-123",
        "master",
    )
    assert result.number == 123
    assert result.url == "https://github.com/posthog/posthog/pull/123"
    assert result.base_branch == "master"


@patch("products.tasks.backend.logic.services.repository_publisher.GitHubIntegration")
@patch("products.tasks.backend.logic.services.repository_publisher.Integration.objects.filter")
def test_create_pull_request_reuses_existing_branch_pull_request(
    filter_integrations: MagicMock,
    github_integration_class: MagicMock,
) -> None:
    filter_integrations.return_value.first.return_value = MagicMock()
    github = github_integration_class.return_value
    github.organization.return_value = "posthog"
    github.get_default_branch.return_value = "master"
    github.list_pull_requests.return_value = {
        "success": True,
        "pull_requests": [
            {
                "number": 123,
                "url": "https://github.com/posthog/posthog/pull/123",
                "head_branch": "posthog/wizard-123",
                "base_branch": "master",
            }
        ],
    }

    result = create_pull_request(
        team_id=7,
        integration_id=13,
        repository="posthog/posthog",
        head_branch="posthog/wizard-123",
        title="Set up PostHog",
        body="Created by the setup agent.",
        source="wizard",
    )

    github.create_pull_request.assert_not_called()
    assert result.number == 123
    assert result.url == "https://github.com/posthog/posthog/pull/123"
