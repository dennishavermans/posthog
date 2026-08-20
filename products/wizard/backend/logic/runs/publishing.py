import shlex
from pathlib import Path

from products.tasks.backend.facade.sandbox import SandboxBase

SIGNED_COMMIT_TIMEOUT_SECONDS = 5 * 60
PUBLISHING_ERROR_DETAIL_LENGTH = 2000
SIGNED_COMMIT_SCRIPT = Path(__file__).with_name("signed_commit.mjs").read_text()


class WizardRepositoryPublishingError(Exception):
    pass


def create_signed_commit(
    sandbox: SandboxBase,
    *,
    repository_path: str,
    branch: str,
    message: str,
) -> str:
    stage_result = sandbox.execute(f"cd {shlex.quote(repository_path)} && git add --all", timeout_seconds=60)
    _raise_for_execution_failure(
        "staging",
        stage_result.exit_code,
        stdout=stage_result.stdout,
        stderr=stage_result.stderr,
    )
    commit_result = sandbox.execute(
        _signed_commit_command(repository_path, branch, message),
        timeout_seconds=SIGNED_COMMIT_TIMEOUT_SECONDS,
    )
    _raise_for_execution_failure(
        "signed commit",
        commit_result.exit_code,
        stdout=commit_result.stdout,
        stderr=commit_result.stderr,
    )
    return branch


def _signed_commit_command(repository_path: str, branch: str, message: str) -> str:
    return " ".join(
        [
            f"remote_url=$(git -C {shlex.quote(repository_path)} remote get-url origin) &&",
            'github_token="${remote_url#https://x-access-token:}" &&',
            'github_token="${github_token%@github.com/*}" &&',
            'test "$github_token" != "$remote_url" &&',
            "cd /scripts &&",
            'GITHUB_TOKEN="$github_token"',
            "node --input-type=module -e",
            shlex.quote(SIGNED_COMMIT_SCRIPT),
            shlex.quote(repository_path),
            shlex.quote(branch),
            shlex.quote(message),
        ]
    )


def _raise_for_execution_failure(stage: str, exit_code: int, *, stdout: str, stderr: str) -> None:
    if exit_code == 0:
        return
    message = f"Repository {stage} failed with exit code {exit_code}."
    detail = (stdout.strip() or stderr.strip())[-PUBLISHING_ERROR_DETAIL_LENGTH:]
    if detail:
        message = f"{message}\n{detail}"
    raise WizardRepositoryPublishingError(message)
