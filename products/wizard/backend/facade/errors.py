class WizardSessionOwnershipError(Exception):
    pass


class MissingGitHubIntegrationError(Exception):
    pass


class RepositoryNotAccessibleError(Exception):
    pass


class InvalidWorkspaceEnvironmentError(Exception):
    pass


class IllegalStatusTransitionError(Exception):
    pass


class InvalidTransitionMetadataError(Exception):
    pass


class WizardRunNotFoundError(Exception):
    pass
