import json

from unittest.mock import patch

from parameterized import parameterized

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import WizardProgram
from products.wizard.backend.facade.enums import WizardRunEnvironment

POSTHOG_INTEGRATION_PROGRAM = WizardProgram(
    id="posthog-integration",
    name="PostHog integration",
    description="Set up PostHog SDK integration",
    command=(),
    tags=(),
    required_programs=(),
    supported_environments=(WizardRunEnvironment.LOCAL, WizardRunEnvironment.CLOUD),
)

AUDIT_PROGRAM_PAYLOAD = {
    "id": "web-analytics-audit",
    "name": "Web analytics audit",
    "description": "Audit a project's web analytics setup",
    "command": ["audit", "web-analytics"],
    "tags": ["audit", "web-analytics"],
    "required_programs": ["posthog-integration"],
    "supported_environments": ["local"],
}


@parameterized.expand(
    [
        ("object", {"version": 1, "programs": [AUDIT_PROGRAM_PAYLOAD]}),
        ("json_string", json.dumps({"version": 1, "programs": [AUDIT_PROGRAM_PAYLOAD]})),
    ]
)
def test_registry_returns_personalized_programs(_name: str, payload: object) -> None:
    with patch("posthoganalytics.get_feature_flag_payload", return_value=payload) as get_payload:
        programs = wizard_facade.get_registry(distinct_id="user-distinct-id", organization_id="organization-id")

    assert programs == (
        WizardProgram(
            id="web-analytics-audit",
            name="Web analytics audit",
            description="Audit a project's web analytics setup",
            command=("audit", "web-analytics"),
            tags=("audit", "web-analytics"),
            required_programs=("posthog-integration",),
            supported_environments=(WizardRunEnvironment.LOCAL,),
        ),
    )
    get_payload.assert_called_once_with(
        "wizard-program-registry",
        distinct_id="user-distinct-id",
        groups={"organization": "organization-id"},
        group_properties={"organization": {"id": "organization-id"}},
        only_evaluate_locally=False,
        send_feature_flag_events=False,
    )


def test_registry_preserves_valid_empty_program_list() -> None:
    with patch("posthoganalytics.get_feature_flag_payload", return_value={"version": 1, "programs": []}):
        programs = wizard_facade.get_registry(distinct_id="user-distinct-id", organization_id="organization-id")

    assert programs == ()


@parameterized.expand(
    [
        ("missing_payload", None),
        ("invalid_json", "{"),
        ("unsupported_version", {"version": 2, "programs": []}),
        ("duplicate_ids", {"version": 1, "programs": [AUDIT_PROGRAM_PAYLOAD, AUDIT_PROGRAM_PAYLOAD]}),
        (
            "invalid_program",
            {
                "version": 1,
                "programs": [
                    AUDIT_PROGRAM_PAYLOAD,
                    {**AUDIT_PROGRAM_PAYLOAD, "id": "invalid-program", "command": ["--override"]},
                ],
            },
        ),
    ]
)
def test_registry_falls_back_when_payload_is_invalid(_name: str, payload: object) -> None:
    with patch("posthoganalytics.get_feature_flag_payload", return_value=payload):
        programs = wizard_facade.get_registry(distinct_id="user-distinct-id", organization_id="organization-id")

    assert programs == (POSTHOG_INTEGRATION_PROGRAM,)


def test_registry_falls_back_when_payload_fetch_fails() -> None:
    with patch("posthoganalytics.get_feature_flag_payload", side_effect=RuntimeError("feature flags unavailable")):
        programs = wizard_facade.get_registry(distinct_id="user-distinct-id", organization_id="organization-id")

    assert programs == (POSTHOG_INTEGRATION_PROGRAM,)
