from products.wizard.backend.facade.contracts import WizardProgram
from products.wizard.backend.facade.validation import (
    validate_nonempty_string,
    validate_program_environments,
    validate_program_id,
    validate_program_ids,
    validate_wizard_version,
)

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


class WizardProgramSerializer:
    def serialize(self, value: WizardProgram) -> dict[str, object]:
        return {
            "id": value.id,
            "name": value.name,
            "description": value.description,
            "wizard_version": value.wizard_version,
            "command": list(value.command),
            "tags": list(value.tags),
            "required_programs": list(value.required_programs),
            "supported_environments": [environment.value for environment in value.supported_environments],
        }

    def deserialize(self, value: object) -> WizardProgram:
        return self._deserialize(value, allow_legacy_version=False)

    def deserialize_persisted(self, value: object) -> WizardProgram:
        return self._deserialize(value, allow_legacy_version=True)

    def _deserialize(self, value: object, *, allow_legacy_version: bool) -> WizardProgram:
        if not isinstance(value, dict) or set(value) != _PROGRAM_FIELDS:
            raise ValueError("Invalid Wizard program")
        return WizardProgram(
            id=validate_program_id(value["id"]),
            name=validate_nonempty_string(value["name"], error="Invalid Wizard program"),
            description=validate_nonempty_string(value["description"], error="Invalid Wizard program"),
            wizard_version=validate_wizard_version(value["wizard_version"], allow_legacy=allow_legacy_version),
            command=validate_program_ids(value["command"]),
            tags=validate_program_ids(value["tags"]),
            required_programs=validate_program_ids(value["required_programs"]),
            supported_environments=validate_program_environments(value["supported_environments"]),
        )


WIZARD_PROGRAM_SERIALIZER = WizardProgramSerializer()
