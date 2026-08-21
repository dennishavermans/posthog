"""
Contract types for wizard.

Frozen dataclasses that define what this product exposes.
No Django imports. Used by facade as inputs/outputs.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol, Self
from uuid import UUID

from posthog.dataclasses import frozen

from .enums import (
    WizardRunArtifactType,
    WizardRunEnvironment,
    WizardRunErrorCode,
    WizardRunStatus,
    WizardSessionRunPhase,
    WizardSessionTaskStatus,
)
from .versions import LEGACY_WIZARD_VERSION, is_exact_wizard_version

STALE_AFTER = timedelta(minutes=10)
_PROGRAM_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PROGRAM_FIELDS = frozenset(
    {
        "id",
        "name",
        "description",
        "wizard_version",
        "command",
        "tags",
        "required_programs",
        "supported_environments",
    }
)
_REGISTRY_FIELDS = frozenset({"version", "programs"})
_WIZARD_REGISTRY_VERSION = 1


class DictSerializable(Protocol):
    def to_dict(self) -> dict[str, object]: ...

    @classmethod
    def from_dict(cls, value: object) -> Self: ...


@dataclass(frozen=True)
class WizardTaskDTO:
    id: str
    title: str
    status: WizardSessionTaskStatus


@dataclass(frozen=True)
class WizardSessionUserDTO:
    id: int
    first_name: str
    email: str


@dataclass(frozen=True)
class WizardSessionDTO:
    session_id: str
    team_id: int
    workflow_id: str
    skill_id: str
    started_at: datetime
    run_phase: WizardSessionRunPhase
    tasks: tuple[WizardTaskDTO, ...]
    event_plan: dict[str, Any] | None
    error: dict[str, Any] | None
    pending_input: dict[str, Any] | None
    handoff_text: str | None
    created_by: WizardSessionUserDTO | None
    created_at: datetime
    updated_at: datetime
    is_stale: bool
    run_id: UUID | None = None


@dataclass(frozen=True)
class UpsertWizardSessionRequest:
    """What the wizard CLI POSTs. team_id is derived from the URL, not the body."""

    session_id: str
    workflow_id: str
    skill_id: str
    started_at: datetime
    run_phase: WizardSessionRunPhase
    tasks: tuple[WizardTaskDTO, ...]
    event_plan: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    pending_input: dict[str, Any] | None = None
    handoff_text: str | None = None
    run_id: UUID | None = None


@dataclass(frozen=True)
class UpsertWizardSessionInput:
    team_id: int
    session_id: str
    workflow_id: str
    skill_id: str
    started_at: datetime
    run_phase: WizardSessionRunPhase
    tasks: tuple[WizardTaskDTO, ...]
    event_plan: dict[str, Any] | None
    error: dict[str, Any] | None
    pending_input: dict[str, Any] | None
    handoff_text: str | None = None
    # Set on create only, never overwritten on later pushes for the same run.
    created_by_id: int | None = None
    run_id: UUID | None = None


@frozen
class LocalFolderWorkspace:
    project_name: str
    type: Literal["local_folder"] = "local_folder"

    def to_dict(self) -> dict[str, object]:
        return {"project_name": self.project_name}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        return cls(project_name=_workspace_metadata_value(value, "project_name"))


@frozen
class GitRepositoryWorkspace:
    repository: str
    type: Literal["git_repository"] = "git_repository"

    def to_dict(self) -> dict[str, object]:
        return {"repository": self.repository}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        return cls(repository=_workspace_metadata_value(value, "repository"))


type WizardWorkspace = LocalFolderWorkspace | GitRepositoryWorkspace


@frozen
class WizardProgram:
    id: str
    name: str
    description: str
    wizard_version: str
    command: tuple[str, ...]
    tags: tuple[str, ...]
    required_programs: tuple[str, ...]
    supported_environments: tuple[WizardRunEnvironment, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "wizard_version": self.wizard_version,
            "command": list(self.command),
            "tags": list(self.tags),
            "required_programs": list(self.required_programs),
            "supported_environments": [environment.value for environment in self.supported_environments],
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        return cls._from_dict(value, allow_legacy_version=False)

    @classmethod
    def from_persisted_dict(cls, value: object) -> Self:
        return cls._from_dict(value, allow_legacy_version=True)

    @classmethod
    def _from_dict(cls, value: object, *, allow_legacy_version: bool) -> Self:
        if not isinstance(value, dict) or set(value) != _PROGRAM_FIELDS:
            raise ValueError("Invalid Wizard program")

        program_id = _program_slug(value["id"])
        name = _program_nonempty_string(value["name"])
        description = _program_nonempty_string(value["description"])
        wizard_version = _program_wizard_version(value["wizard_version"], allow_legacy_version=allow_legacy_version)
        command = _program_slug_list(value["command"])
        tags = _program_slug_list(value["tags"])
        required_programs = _program_slug_list(value["required_programs"])
        supported_environments = _program_environments(value["supported_environments"])
        if not supported_environments:
            raise ValueError("Invalid Wizard program")

        return cls(
            id=program_id,
            name=name,
            description=description,
            wizard_version=wizard_version,
            command=command,
            tags=tags,
            required_programs=required_programs,
            supported_environments=supported_environments,
        )


@frozen
class WizardRegistry:
    programs: tuple[WizardProgram, ...]
    version: Literal[1] = 1

    def to_dict(self) -> dict[str, object]:
        return {"version": self.version, "programs": [program.to_dict() for program in self.programs]}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        if not isinstance(value, dict) or set(value) != _REGISTRY_FIELDS:
            raise ValueError("Invalid Wizard registry")
        if type(value["version"]) is not int or value["version"] != _WIZARD_REGISTRY_VERSION:
            raise ValueError("Invalid Wizard registry")
        if not isinstance(value["programs"], list):
            raise ValueError("Invalid Wizard registry")

        programs = tuple(WizardProgram.from_dict(program) for program in value["programs"])
        if len(programs) != len({program.id for program in programs}):
            raise ValueError("Invalid Wizard registry")
        return cls(programs=programs)


@frozen
class CreateWizardRunInput:
    team_id: int
    created_by_id: int
    environment: WizardRunEnvironment
    workspace: WizardWorkspace
    program_id: str


@frozen
class WizardRunDTO:
    id: UUID
    team_id: int
    created_by_id: int | None
    environment: WizardRunEnvironment
    workspace: WizardWorkspace
    program: WizardProgram
    status: WizardRunStatus
    error_code: WizardRunErrorCode | None


@frozen
class ListWizardRunsInput:
    team_id: int
    offset: int
    limit: int


@frozen
class WizardRunPage:
    results: tuple[WizardRunDTO, ...]
    count: int


@frozen
class CreatePullRequestArtifactInput:
    team_id: int
    run_id: UUID
    url: str
    number: int
    repository: str
    head_branch: str
    base_branch: str


@frozen
class WizardRunGitDiffArtifactDTO:
    id: UUID
    team_id: int
    run_id: UUID
    artifact_type: Literal[WizardRunArtifactType.GIT_DIFF]
    size_bytes: int
    content_hash: str
    created_at: datetime


@frozen
class WizardRunPullRequestArtifactDTO:
    id: UUID
    team_id: int
    run_id: UUID
    artifact_type: Literal[WizardRunArtifactType.PULL_REQUEST]
    url: str
    number: int
    repository: str
    head_branch: str
    base_branch: str
    created_at: datetime


type WizardRunArtifactDTO = WizardRunGitDiffArtifactDTO | WizardRunPullRequestArtifactDTO


def _program_nonempty_string(value: object) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError("Invalid Wizard program")
    return value


def _program_slug(value: object) -> str:
    if not isinstance(value, str) or _PROGRAM_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("Invalid Wizard program")
    return value


def _program_wizard_version(value: object, *, allow_legacy_version: bool) -> str:
    if allow_legacy_version and value == LEGACY_WIZARD_VERSION:
        return LEGACY_WIZARD_VERSION
    if not isinstance(value, str) or not is_exact_wizard_version(value):
        raise ValueError("Invalid Wizard program")
    return value


def _program_slug_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("Invalid Wizard program")
    values = tuple(_program_slug(item) for item in value)
    if len(values) != len(set(values)):
        raise ValueError("Invalid Wizard program")
    return values


def _program_environments(value: object) -> tuple[WizardRunEnvironment, ...]:
    if not isinstance(value, list):
        raise ValueError("Invalid Wizard program")
    try:
        environments = tuple(WizardRunEnvironment(item) for item in value)
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid Wizard program") from error
    if len(environments) != len(set(environments)):
        raise ValueError("Invalid Wizard program")
    return environments


def _workspace_metadata_value(metadata: object, key: str) -> str:
    if not isinstance(metadata, dict):
        raise ValueError("Wizard workspace metadata must be an object")

    value: object = metadata.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Wizard workspace metadata field {key!r} must be a string")
    return value
