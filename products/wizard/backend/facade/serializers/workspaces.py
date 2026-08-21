from products.wizard.backend.facade.contracts import GitRepositoryWorkspace, LocalFolderWorkspace, WizardWorkspace
from products.wizard.backend.facade.enums import WizardWorkspaceType
from products.wizard.backend.facade.validation import validate_workspace_metadata_value


class WizardWorkspaceSerializer:
    def serialize(self, value: WizardWorkspace) -> tuple[WizardWorkspaceType, dict[str, object]]:
        match value:
            case LocalFolderWorkspace(project_name=project_name):
                return WizardWorkspaceType.LOCAL_FOLDER, {"project_name": project_name}
            case GitRepositoryWorkspace(repository=repository):
                return WizardWorkspaceType.GIT_REPOSITORY, {"repository": repository}

    def deserialize(self, workspace_type: str, metadata: object) -> WizardWorkspace:
        match WizardWorkspaceType(workspace_type):
            case WizardWorkspaceType.LOCAL_FOLDER:
                return LocalFolderWorkspace(project_name=validate_workspace_metadata_value(metadata, "project_name"))
            case WizardWorkspaceType.GIT_REPOSITORY:
                return GitRepositoryWorkspace(repository=validate_workspace_metadata_value(metadata, "repository"))


WIZARD_WORKSPACE_SERIALIZER = WizardWorkspaceSerializer()
