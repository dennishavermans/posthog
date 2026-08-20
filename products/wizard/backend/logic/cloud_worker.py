import shlex
from uuid import UUID

from django.conf import settings

from posthog.dataclasses import frozen
from posthog.models.user import User
from posthog.temporal.oauth import create_wizard_oauth_access_token_for_user
from posthog.utils import get_instance_region

from products.tasks.backend.facade import repository as repository_facade
from products.tasks.backend.facade.repo_selection import get_github_token
from products.tasks.backend.facade.sandbox import (
    SandboxConfig,
    SandboxNotFoundError,
    SandboxTemplate,
    get_sandbox_class,
    sandbox_repo_path,
)

WIZARD_PACKAGE = "@posthog/wizard@latest"
WIZARD_TIMEOUT_SECONDS = 45 * 60
WIZARD_TIMEOUT_EXIT_CODE = 124
SANDBOX_EXECUTION_TIMEOUT_SECONDS = WIZARD_TIMEOUT_SECONDS + 120
SANDBOX_TTL_SECONDS = WIZARD_TIMEOUT_SECONDS + 300
PULL_REQUEST_TITLE = "Set up PostHog"
PULL_REQUEST_BODY = "This pull request contains changes created by Wizard, PostHog's setup agent."
PULL_REQUEST_COMMIT_MESSAGE = "Set up PostHog"


@frozen
class WizardWorkerProvisionRequest:
    team_id: int
    created_by_id: int
    run_id: UUID


@frozen
class GitRepositoryCloneRequest:
    sandbox_id: str
    github_integration_id: int
    repository: str


@frozen
class WizardExecutionRequest:
    sandbox_id: str
    workspace_path: str
    team_id: int


@frozen
class GitRepositoryHandoffRequest:
    team_id: int
    run_id: UUID
    sandbox_id: str
    workspace_path: str
    github_integration_id: int
    repository: str


@frozen
class WizardWorkerResult:
    diff: bytes
    pull_request: repository_facade.RepositoryPullRequest | None


class WizardWorkerExecutionError(Exception):
    def __init__(self, stage: str, exit_code: int) -> None:
        self.stage = stage
        self.exit_code = exit_code
        super().__init__(f"Wizard Worker {stage} failed with exit code {exit_code}.")


class WizardWorkerTimeoutError(Exception):
    pass


def provision_worker(request: WizardWorkerProvisionRequest) -> str:
    user = User.objects.get(id=request.created_by_id)
    wizard_token = create_wizard_oauth_access_token_for_user(user, request.team_id)
    config = SandboxConfig(
        name=f"wizard-{request.run_id}",
        template=SandboxTemplate.DEFAULT_BASE,
        default_execution_timeout_seconds=SANDBOX_EXECUTION_TIMEOUT_SECONDS,
        ttl_seconds=SANDBOX_TTL_SECONDS,
        memory_gb=4,
        cpu_cores=2,
        disk_size_gb=16,
        environment_variables={
            "POSTHOG_API_URL": settings.SANDBOX_API_URL or settings.SITE_URL,
            "POSTHOG_PROJECT_ID": str(request.team_id),
            "POSTHOG_WIZARD_API_KEY": wizard_token,
            "POSTHOG_WIZARD_RUN_ID": str(request.run_id),
        },
        metadata={
            "purpose": "wizard_run",
            "team_id": str(request.team_id),
            "wizard_run_id": str(request.run_id),
        },
    )
    return get_sandbox_class().create(config).id


def clone_repository(request: GitRepositoryCloneRequest) -> str:
    sandbox = get_sandbox_class().get_by_id(request.sandbox_id)
    github_token = get_github_token(request.github_integration_id) or ""
    clone_result = sandbox.clone_repository(request.repository, github_token=github_token, shallow=True)
    _raise_for_failure("repository clone", clone_result.exit_code)
    return sandbox_repo_path(request.repository)


def execute_wizard(request: WizardExecutionRequest) -> None:
    sandbox = get_sandbox_class().get_by_id(request.sandbox_id)
    wizard_result = sandbox.execute(
        _wizard_command(request.workspace_path, request.team_id),
        timeout_seconds=SANDBOX_EXECUTION_TIMEOUT_SECONDS,
    )
    if wizard_result.exit_code == WIZARD_TIMEOUT_EXIT_CODE:
        raise WizardWorkerTimeoutError
    _raise_for_failure("execution", wizard_result.exit_code)


def create_git_repository_handoff(request: GitRepositoryHandoffRequest) -> WizardWorkerResult:
    sandbox = get_sandbox_class().get_by_id(request.sandbox_id)
    diff_result = sandbox.execute(
        _git_diff_command(request.workspace_path),
        timeout_seconds=60,
    )
    _raise_for_failure("diff capture", diff_result.exit_code)
    diff = diff_result.stdout.encode("utf-8")
    if not diff:
        return WizardWorkerResult(diff=diff, pull_request=None)

    branch = _pull_request_branch(request.run_id)
    try:
        commit = repository_facade.create_signed_commit(
            sandbox,
            repository=request.repository,
            branch=branch,
            message=PULL_REQUEST_COMMIT_MESSAGE,
        )
        pull_request = repository_facade.create_pull_request(
            team_id=request.team_id,
            integration_id=request.github_integration_id,
            repository=request.repository,
            head_branch=commit.branch,
            title=PULL_REQUEST_TITLE,
            body=PULL_REQUEST_BODY,
            source="wizard",
        )
    except repository_facade.RepositoryPublishingError as error:
        raise WizardWorkerExecutionError("publishing", 1) from error
    return WizardWorkerResult(diff=diff, pull_request=pull_request)


def destroy_worker(sandbox_id: str) -> None:
    try:
        sandbox = get_sandbox_class().get_by_id(sandbox_id)
    except SandboxNotFoundError:
        return
    sandbox.destroy()


def _wizard_command(repository_path: str, team_id: int) -> str:
    parts = [
        f"cd {shlex.quote(repository_path)} &&",
        f"timeout -k 30 {WIZARD_TIMEOUT_SECONDS}",
        f"npx --yes {WIZARD_PACKAGE}",
        "--headless-DONOTUSE-EXPERIMENTAL",
        "--install-dir .",
        f"--region {shlex.quote(_wizard_region())}",
        f"--project-id {shlex.quote(str(team_id))}",
    ]
    if settings.DEBUG:
        parts.append('--base-url "$POSTHOG_API_URL"')
    return " ".join(parts)


def _git_diff_command(repository_path: str) -> str:
    return f"cd {shlex.quote(repository_path)} && git add -N --all && git diff --binary --no-ext-diff HEAD"


def _pull_request_branch(run_id: UUID) -> str:
    return f"posthog/wizard-{run_id.hex[:12]}"


def _wizard_region() -> str:
    return "eu" if get_instance_region() == "EU" else "us"


def _raise_for_failure(stage: str, exit_code: int) -> None:
    if exit_code != 0:
        raise WizardWorkerExecutionError(stage, exit_code)
