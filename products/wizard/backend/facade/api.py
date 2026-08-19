"""
Facade for wizard.

The ONLY module other products are allowed to import.
Accept frozen dataclasses, call logic/, return frozen
dataclasses. Never return ORM instances or import DRF.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from products.wizard.backend import metrics
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    UpsertWizardSessionInput,
    WizardRunArtifactDTO,
    WizardRunDTO,
    WizardSessionDTO,
)
from products.wizard.backend.facade.enums import WizardRunErrorCode
from products.wizard.backend.logic import (
    artifacts,
    pubsub,
    runs as run_service,
    sessions,
)


def upsert(params: UpsertWizardSessionInput) -> tuple[WizardSessionDTO, bool]:
    """Returns `(dto, created)` so callers can pick 201 vs 200."""
    return sessions.upsert_session(params)


def get(team_id: int, session_id: str) -> WizardSessionDTO | None:
    return sessions.get_session(team_id, session_id)


def get_latest(team_id: int, workflow_id: str, skill_id: str | None = None) -> WizardSessionDTO | None:
    return sessions.get_latest_session(team_id, workflow_id, skill_id)


def list_for_team(
    team_id: int,
    workflow_id: str | None = None,
    skill_id: str | None = None,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[WizardSessionDTO]:
    return sessions.list_sessions(
        team_id,
        workflow_id=workflow_id,
        skill_id=skill_id,
        offset=offset,
        limit=limit,
    )


@asynccontextmanager
async def subscribe_to_updates(
    team_id: int,
    workflow_id: str,
    skill_id: str | None = None,
) -> AsyncIterator[Any]:
    async with pubsub.subscribe(team_id, workflow_id, skill_id) as ps:
        yield ps


def serialize_dto(dto: WizardSessionDTO) -> bytes:
    return pubsub.serialize_dto(dto)


def record_latest_session_poll(raw_source: str | None, result: str) -> None:
    metrics.WIZARD_LATEST_SESSION_REQUESTS_TOTAL.labels(
        source=metrics.poll_source_label(raw_source), result=result
    ).inc()


# Wizard Runs API


def create_run(params: CreateWizardRunInput) -> WizardRunDTO:
    return run_service.create_run(params)


def get_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    return run_service.get_run(team_id, run_id)


def start_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    return run_service.start_run(team_id, run_id)


def complete_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    return run_service.complete_run(team_id, run_id)


def fail_run(
    team_id: int,
    run_id: UUID,
    *,
    error_code: WizardRunErrorCode | None = None,
) -> WizardRunDTO:
    return run_service.fail_run(team_id, run_id, error_code=error_code)


def cancel_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    return run_service.cancel_run(team_id, run_id)


def create_git_diff_artifact(team_id: int, run_id: UUID, content: bytes) -> WizardRunArtifactDTO | None:
    return artifacts.create_git_diff_artifact(team_id, run_id, content)


def list_run_artifacts(team_id: int, run_id: UUID) -> list[WizardRunArtifactDTO]:
    return artifacts.list_run_artifacts(team_id, run_id)


def validate_git_repository(repository: str) -> None:
    run_service.validate_git_repository(repository)
