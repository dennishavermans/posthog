import pytest

from posthog.models import Team

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import CreateWizardRunInput, LocalFolderWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment
from products.wizard.backend.facade.errors import WizardRunNotFoundError


@pytest.mark.django_db
def test_get_run_is_scoped_to_team(team, user) -> None:
    other_team = Team.objects.create(organization=team.organization, project=team.project, name="Other environment")
    created = wizard_facade.create_run(
        CreateWizardRunInput(
            team_id=team.id,
            created_by_id=user.id,
            environment=WizardRunEnvironment.LOCAL,
            workspace=LocalFolderWorkspace(project_name="example-project"),
        )
    )

    assert wizard_facade.get_run(team.id, created.id) == created

    with pytest.raises(WizardRunNotFoundError):
        wizard_facade.get_run(other_team.id, created.id)
