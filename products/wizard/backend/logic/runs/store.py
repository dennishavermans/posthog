from uuid import UUID

from products.wizard.backend.facade.errors import WizardRunNotFoundError
from products.wizard.backend.models import WizardRun


def get_run_model(team_id: int, run_id: UUID, *, lock: bool = False) -> WizardRun:
    runs = WizardRun.objects.for_team(team_id)
    if lock:
        runs = runs.select_for_update()

    run = runs.filter(id=run_id).first()
    if run is None:
        raise WizardRunNotFoundError

    return run
