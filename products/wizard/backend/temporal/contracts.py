from uuid import UUID

from posthog.dataclasses import frozen


@frozen
class WizardRunActivityInput:
    team_id: int
    run_id: UUID
