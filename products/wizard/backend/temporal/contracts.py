from uuid import UUID

from posthog.dataclasses import frozen

from products.wizard.backend.facade.enums import WizardRunErrorCode, WizardWorkspaceType


@frozen
class WizardRunActivityInput:
    team_id: int
    run_id: UUID


@frozen
class WizardRunFailureActivityInput:
    team_id: int
    run_id: UUID
    error_code: WizardRunErrorCode


@frozen
class ProvisionedWizardWorker:
    team_id: int
    run_id: UUID
    sandbox_id: str
    workspace_type: WizardWorkspaceType


@frozen
class PreparedGitRepositoryWorkspace:
    team_id: int
    run_id: UUID
    sandbox_id: str
    repository: str
    root_path: str
    github_integration_id: int
