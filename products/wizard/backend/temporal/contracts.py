from uuid import UUID

from posthog.dataclasses import frozen

from products.wizard.backend.facade.enums import WizardRunErrorCode


@frozen
class WizardRunActivityInput:
    team_id: int
    run_id: UUID


@frozen
class WizardRunFailureActivityInput:
    team_id: int
    run_id: UUID
    error_code: WizardRunErrorCode
