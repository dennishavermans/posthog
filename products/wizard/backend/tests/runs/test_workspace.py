import pytest

from products.wizard.backend.facade.contracts import GitRepositoryWorkspace, LocalFolderWorkspace, WizardWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment
from products.wizard.backend.facade.errors import InvalidWorkspaceEnvironmentError
from products.wizard.backend.logic.runs.workspaces import validate_workspace_environment


@pytest.mark.parametrize(
    ("environment", "workspace"),
    [
        (WizardRunEnvironment.LOCAL, LocalFolderWorkspace(project_name="example-project")),
        (WizardRunEnvironment.CLOUD, GitRepositoryWorkspace(repository="posthog/posthog")),
    ],
)
def test_environment_accepts_supported_workspace(environment: WizardRunEnvironment, workspace: WizardWorkspace) -> None:
    validate_workspace_environment(environment, workspace)


@pytest.mark.parametrize(
    ("environment", "workspace"),
    [
        (WizardRunEnvironment.LOCAL, GitRepositoryWorkspace(repository="posthog/posthog")),
        (WizardRunEnvironment.CLOUD, LocalFolderWorkspace(project_name="example-project")),
    ],
)
def test_environment_rejects_unsupported_workspace(
    environment: WizardRunEnvironment, workspace: WizardWorkspace
) -> None:
    with pytest.raises(InvalidWorkspaceEnvironmentError):
        validate_workspace_environment(environment, workspace)
