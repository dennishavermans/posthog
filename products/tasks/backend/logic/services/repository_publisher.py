import json
import shlex

from posthog.dataclasses import frozen
from posthog.models.integration import GitHubIntegration, Integration

from products.tasks.backend.logic.services.sandbox import SandboxBase, sandbox_repo_path

SIGNED_COMMIT_TIMEOUT_SECONDS = 5 * 60
SIGNED_COMMIT_SCRIPT = (
    'import { createSignedCommit } from "@posthog/git/signed-commit";'
    "const result = await createSignedCommit("
    "{ cwd: process.argv[1], token: process.env.GITHUB_TOKEN },"
    "{ branch: process.argv[2], message: process.argv[3] }"
    ");"
    "process.stdout.write(JSON.stringify(result));"
)


@frozen
class SignedRepositoryCommit:
    repository: str
    branch: str
    commit_shas: tuple[str, ...]


@frozen
class RepositoryPullRequest:
    repository: str
    number: int
    url: str
    head_branch: str
    base_branch: str


class RepositoryPublishingError(Exception):
    pass


def create_signed_commit(
    sandbox: SandboxBase,
    *,
    repository: str,
    branch: str,
    message: str,
) -> SignedRepositoryCommit:
    repository_path = sandbox_repo_path(repository)
    stage_result = sandbox.execute(f"cd {shlex.quote(repository_path)} && git add --all", timeout_seconds=60)
    _raise_for_execution_failure("staging", stage_result.exit_code)
    commit_result = sandbox.execute(
        _signed_commit_command(repository_path, branch, message),
        timeout_seconds=SIGNED_COMMIT_TIMEOUT_SECONDS,
    )
    _raise_for_execution_failure("signed commit", commit_result.exit_code)
    return _parse_signed_commit(commit_result.stdout, repository, branch)


def create_pull_request(
    *,
    team_id: int,
    integration_id: int,
    repository: str,
    head_branch: str,
    title: str,
    body: str,
    source: str,
) -> RepositoryPullRequest:
    owner, repository_name = _repository_parts(repository)
    integration = Integration.objects.filter(team_id=team_id, id=integration_id, kind="github").first()
    if integration is None:
        raise RepositoryPublishingError("GitHub integration is unavailable.")

    github = GitHubIntegration(integration, source=source)
    if github.organization().casefold() != owner.casefold():
        raise RepositoryPublishingError("GitHub integration does not own the repository.")

    base_branch = github.get_default_branch(repository_name)
    existing = _matching_pull_request(
        github.list_pull_requests(repository_name),
        repository,
        head_branch,
        base_branch,
    )
    if existing is not None:
        return existing

    created = github.create_pull_request(repository_name, title, body, head_branch, base_branch)
    return _created_pull_request(created, repository, head_branch, base_branch)


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


def _parse_signed_commit(stdout: str, repository: str, branch: str) -> SignedRepositoryCommit:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise RepositoryPublishingError("Signed commit returned an invalid result.") from error
    if not isinstance(payload, dict):
        raise RepositoryPublishingError("Signed commit returned an invalid result.")

    result_repository = payload.get("repository")
    result_branch = payload.get("branch")
    commits = payload.get("commits")
    if (
        not isinstance(result_repository, str)
        or result_repository.casefold() != repository.casefold()
        or result_branch != branch
        or not isinstance(commits, list)
    ):
        raise RepositoryPublishingError("Signed commit returned an invalid result.")

    commit_shas: list[str] = []
    for commit in commits:
        if not isinstance(commit, dict):
            raise RepositoryPublishingError("Signed commit returned an invalid result.")
        commit_sha = commit.get("sha")
        if not isinstance(commit_sha, str):
            raise RepositoryPublishingError("Signed commit returned an invalid result.")
        commit_shas.append(commit_sha)
    return SignedRepositoryCommit(
        repository=result_repository,
        branch=result_branch,
        commit_shas=tuple(commit_shas),
    )


def _repository_parts(repository: str) -> tuple[str, str]:
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise RepositoryPublishingError("Repository must use owner/name format.")
    return parts[0], parts[1]


def _matching_pull_request(
    payload: object,
    repository: str,
    head_branch: str,
    base_branch: str,
) -> RepositoryPullRequest | None:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return None
    pull_requests = payload.get("pull_requests")
    if not isinstance(pull_requests, list):
        return None
    for value in pull_requests:
        if not isinstance(value, dict) or value.get("head_branch") != head_branch:
            continue
        number = value.get("number")
        url = value.get("url")
        pull_request_base_branch = value.get("base_branch")
        if isinstance(number, int) and isinstance(url, str):
            return RepositoryPullRequest(
                repository=repository,
                number=number,
                url=url,
                head_branch=head_branch,
                base_branch=pull_request_base_branch if isinstance(pull_request_base_branch, str) else base_branch,
            )
    return None


def _created_pull_request(
    payload: object,
    repository: str,
    head_branch: str,
    base_branch: str,
) -> RepositoryPullRequest:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RepositoryPublishingError("GitHub did not create the pull request.")
    number = payload.get("pr_number")
    url = payload.get("pr_url")
    if not isinstance(number, int) or not isinstance(url, str):
        raise RepositoryPublishingError("GitHub returned an invalid pull request.")
    return RepositoryPullRequest(
        repository=repository,
        number=number,
        url=url,
        head_branch=head_branch,
        base_branch=base_branch,
    )


def _raise_for_execution_failure(stage: str, exit_code: int) -> None:
    if exit_code != 0:
        raise RepositoryPublishingError(f"Repository {stage} failed with exit code {exit_code}.")
