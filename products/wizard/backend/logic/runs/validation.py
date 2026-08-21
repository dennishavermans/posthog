from products.wizard.backend.facade.errors import InvalidRepositoryError


def validate_git_repository(repository: str) -> None:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise InvalidRepositoryError
