import json
import logging

import posthoganalytics

from products.wizard.backend.facade.contracts import WizardProgram
from products.wizard.backend.facade.enums import WizardRunEnvironment
from products.wizard.backend.facade.errors import WizardProgramNotAvailableError
from products.wizard.backend.facade.versions import DEFAULT_WIZARD_VERSION

REGISTRY_FEATURE_FLAG = "wizard-program-registry"
REGISTRY_VERSION = 1
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
        try:
            program = WizardProgram.from_dict(raw_program)
        except ValueError:
            return None
        if program.id in program_ids:
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
