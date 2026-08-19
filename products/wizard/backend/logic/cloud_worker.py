import shlex
from uuid import UUID

from django.conf import settings

from posthog.dataclasses import frozen
from posthog.models.user import User
from posthog.temporal.oauth import create_wizard_oauth_access_token_for_user
from posthog.utils import get_instance_region

from products.tasks.backend.facade.repo_selection import get_github_token
from products.tasks.backend.facade.sandbox import SandboxConfig, SandboxTemplate, get_sandbox_class, sandbox_repo_path

WIZARD_PACKAGE = "@posthog/wizard@latest"
WIZARD_TIMEOUT_SECONDS = 45 * 60
WIZARD_TIMEOUT_EXIT_CODE = 124
SANDBOX_EXECUTION_TIMEOUT_SECONDS = WIZARD_TIMEOUT_SECONDS + 120
SANDBOX_TTL_SECONDS = WIZARD_TIMEOUT_SECONDS + 300


@frozen
class WizardWorkerInput:
    team_id: int
    created_by_id: int
    run_id: UUID
    github_integration_id: int
    repository: str


class WizardWorkerExecutionError(Exception):
    def __init__(self, stage: str, exit_code: int) -> None:
        self.stage = stage
        self.exit_code = exit_code
        super().__init__(f"Wizard Worker {stage} failed with exit code {exit_code}.")


class WizardWorkerTimeoutError(Exception):
    pass


def execute_wizard_worker(input: WizardWorkerInput) -> bytes:
    user = User.objects.get(id=input.created_by_id)
    github_token = get_github_token(input.github_integration_id) or ""
    wizard_token = create_wizard_oauth_access_token_for_user(user, input.team_id)
    repository_path = sandbox_repo_path(input.repository)
    config = SandboxConfig(
        name=f"wizard-{input.run_id}",
        template=SandboxTemplate.DEFAULT_BASE,
        default_execution_timeout_seconds=SANDBOX_EXECUTION_TIMEOUT_SECONDS,
        ttl_seconds=SANDBOX_TTL_SECONDS,
        memory_gb=4,
        cpu_cores=2,
        disk_size_gb=16,
        environment_variables={
            "GITHUB_TOKEN": github_token,
            "POSTHOG_API_URL": settings.SANDBOX_API_URL or settings.SITE_URL,
            "POSTHOG_PROJECT_ID": str(input.team_id),
            "POSTHOG_WIZARD_API_KEY": wizard_token,
            "POSTHOG_WIZARD_RUN_ID": str(input.run_id),
        },
        metadata={
            "purpose": "wizard_run",
            "team_id": str(input.team_id),
            "wizard_run_id": str(input.run_id),
        },
    )
    sandbox = get_sandbox_class().create(config)

    try:
        clone_result = sandbox.clone_repository(input.repository, github_token=github_token, shallow=True)
        _raise_for_failure("repository clone", clone_result.exit_code)

        wizard_result = sandbox.execute(
            _wizard_command(repository_path, input.team_id),
            timeout_seconds=SANDBOX_EXECUTION_TIMEOUT_SECONDS,
        )
        if wizard_result.exit_code == WIZARD_TIMEOUT_EXIT_CODE:
            raise WizardWorkerTimeoutError
        _raise_for_failure("execution", wizard_result.exit_code)

        diff_result = sandbox.execute(
            _git_diff_command(repository_path),
            timeout_seconds=60,
        )
        _raise_for_failure("diff capture", diff_result.exit_code)
        return diff_result.stdout.encode("utf-8")
    finally:
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


def _wizard_region() -> str:
    return "eu" if get_instance_region() == "EU" else "us"


def _raise_for_failure(stage: str, exit_code: int) -> None:
    if exit_code != 0:
        raise WizardWorkerExecutionError(stage, exit_code)
