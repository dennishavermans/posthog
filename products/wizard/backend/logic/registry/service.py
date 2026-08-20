import re
import json
import logging

import posthoganalytics

from products.wizard.backend.facade.contracts import WizardProgram
from products.wizard.backend.facade.enums import WizardRunEnvironment
from products.wizard.backend.facade.errors import WizardProgramNotAvailableError
from products.wizard.backend.logic.registry.versions import (
    DEFAULT_WIZARD_VERSION,
    LEGACY_WIZARD_VERSION,
    is_exact_wizard_version,
)

REGISTRY_FEATURE_FLAG = "wizard-program-registry"
REGISTRY_VERSION = 2
PROGRAM_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROGRAM_FIELDS = {
    "id",
    "name",
    "description",
    "wizard_version",
    "command",
    "tags",
    "required_programs",
    "supported_environments",
}
POSTHOG_INTEGRATION_PROGRAM = WizardProgram(
    id="posthog-integration",
    name="PostHog integration",
    description="Set up PostHog SDK integration",
    wizard_version=DEFAULT_WIZARD_VERSION,
    command=(),
    tags=(),
    required_programs=(),
    supported_environments=(WizardRunEnvironment.LOCAL, WizardRunEnvironment.CLOUD),
)
FALLBACK_REGISTRY = (POSTHOG_INTEGRATION_PROGRAM,)

logger = logging.getLogger(__name__)


def get_registry(*, distinct_id: str, organization_id: str) -> tuple[WizardProgram, ...]:
    try:
        payload = posthoganalytics.get_feature_flag_payload(
            REGISTRY_FEATURE_FLAG,
            distinct_id=distinct_id,
            groups={"organization": organization_id},
            group_properties={"organization": {"id": organization_id}},
            only_evaluate_locally=False,
            send_feature_flag_events=False,
        )
    except Exception:
        logger.exception("wizard_registry_fetch_failed")
        return FALLBACK_REGISTRY

    registry = _parse_registry(payload)
    if registry is None:
        return FALLBACK_REGISTRY
    return registry


def get_program(*, program_id: str, distinct_id: str, organization_id: str) -> WizardProgram:
    programs = get_registry(distinct_id=distinct_id, organization_id=organization_id)
    program = next((program for program in programs if program.id == program_id), None)
    if program is None:
        raise WizardProgramNotAvailableError
    return program


def serialize_program(program: WizardProgram) -> dict[str, object]:
    return {
        "id": program.id,
        "name": program.name,
        "description": program.description,
        "wizard_version": program.wizard_version,
        "command": list(program.command),
        "tags": list(program.tags),
        "required_programs": list(program.required_programs),
        "supported_environments": [environment.value for environment in program.supported_environments],
    }


def deserialize_program(value: object) -> WizardProgram:
    program = _parse_program(value, allow_legacy_version=True)
    if program is None:
        raise ValueError("Invalid persisted Wizard program")
    return program


def _parse_registry(payload: object) -> tuple[WizardProgram, ...] | None:
    decoded = _decode_payload(payload)
    if not isinstance(decoded, dict) or set(decoded) != {"version", "programs"}:
        return None
    if type(decoded["version"]) is not int or decoded["version"] != REGISTRY_VERSION:
        return None

    raw_programs = decoded["programs"]
    if not isinstance(raw_programs, list):
        return None

    programs: list[WizardProgram] = []
    program_ids: set[str] = set()
    for raw_program in raw_programs:
        program = _parse_program(raw_program)
        if program is None or program.id in program_ids:
            return None
        programs.append(program)
        program_ids.add(program.id)
    return tuple(programs)


def _decode_payload(payload: object) -> object:
    if not isinstance(payload, str):
        return payload
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return None


def _parse_program(value: object, *, allow_legacy_version: bool = False) -> WizardProgram | None:
    if not isinstance(value, dict) or set(value) != PROGRAM_FIELDS:
        return None

    program_id = _parse_slug(value["id"])
    name = _parse_nonempty_string(value["name"])
    description = _parse_nonempty_string(value["description"])
    wizard_version = _parse_wizard_version(value["wizard_version"], allow_legacy=allow_legacy_version)
    command = _parse_slug_list(value["command"])
    tags = _parse_slug_list(value["tags"])
    required_programs = _parse_slug_list(value["required_programs"])
    supported_environments = _parse_environments(value["supported_environments"])
    if (
        program_id is None
        or name is None
        or description is None
        or wizard_version is None
        or command is None
        or tags is None
        or required_programs is None
        or supported_environments is None
        or not supported_environments
    ):
        return None

    return WizardProgram(
        id=program_id,
        name=name,
        description=description,
        wizard_version=wizard_version,
        command=command,
        tags=tags,
        required_programs=required_programs,
        supported_environments=supported_environments,
    )


def _parse_nonempty_string(value: object) -> str | None:
    if not isinstance(value, str) or value != value.strip() or not value:
        return None
    return value


def _parse_slug(value: object) -> str | None:
    if not isinstance(value, str) or PROGRAM_ID_PATTERN.fullmatch(value) is None:
        return None
    return value


def _parse_wizard_version(value: object, *, allow_legacy: bool) -> str | None:
    if not isinstance(value, str):
        return None
    if allow_legacy and value == LEGACY_WIZARD_VERSION:
        return value
    if not is_exact_wizard_version(value):
        return None
    return value


def _parse_slug_list(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    values: list[str] = []
    for item in value:
        parsed = _parse_slug(item)
        if parsed is None or parsed in values:
            return None
        values.append(parsed)
    return tuple(values)


def _parse_environments(value: object) -> tuple[WizardRunEnvironment, ...] | None:
    if not isinstance(value, list):
        return None
    environments: list[WizardRunEnvironment] = []
    for item in value:
        if not isinstance(item, str):
            return None
        try:
            environment = WizardRunEnvironment(item)
        except ValueError:
            return None
        if environment in environments:
            return None
        environments.append(environment)
    return tuple(environments)
