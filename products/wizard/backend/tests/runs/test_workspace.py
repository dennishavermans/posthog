import pytest

from products.wizard.backend.facade.contracts import GitRepositoryWorkspace, LocalFolderWorkspace, WizardWorkspace
from products.wizard.backend.facade.enums import WizardWorkspaceType
from products.wizard.backend.facade.serializers.workspaces import WIZARD_WORKSPACE_SERIALIZER


@pytest.mark.parametrize(
    ("workspace_type", "metadata", "expected_workspace"),
    [
        (
            WizardWorkspaceType.LOCAL_FOLDER,
            {"project_name": "example-project"},
            LocalFolderWorkspace(project_name="example-project"),
        ),
        (
            WizardWorkspaceType.GIT_REPOSITORY,
            {"repository": "posthog/posthog"},
            GitRepositoryWorkspace(repository="posthog/posthog"),
        ),
    ],
)
def test_workspace_serialization_round_trip(
    workspace_type: WizardWorkspaceType,
    metadata: dict[str, str],
    expected_workspace: WizardWorkspace,
) -> None:
    workspace = WIZARD_WORKSPACE_SERIALIZER.deserialize(workspace_type.value, metadata)

    assert workspace == expected_workspace
    assert WIZARD_WORKSPACE_SERIALIZER.serialize(workspace) == (workspace_type, metadata)


@pytest.mark.parametrize(
    ("workspace_type", "metadata"),
    [
        (WizardWorkspaceType.LOCAL_FOLDER, {"project_name": 123}),
        (WizardWorkspaceType.GIT_REPOSITORY, {"repository": None}),
    ],
)
def test_workspace_rejects_invalid_serialized_value(
    workspace_type: WizardWorkspaceType, metadata: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        WIZARD_WORKSPACE_SERIALIZER.deserialize(workspace_type.value, metadata)
