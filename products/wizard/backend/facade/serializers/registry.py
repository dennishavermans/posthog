import json

from products.wizard.backend.facade.config import WIZARD_REGISTRY_VERSION
from products.wizard.backend.facade.contracts import WizardRegistry
from products.wizard.backend.facade.serializers.programs import WIZARD_PROGRAM_SERIALIZER

_REGISTRY_FIELDS = frozenset({"version", "programs"})


class WizardRegistrySerializer:
    def serialize(self, value: WizardRegistry) -> dict[str, object]:
        return {
            "version": value.version,
            "programs": [WIZARD_PROGRAM_SERIALIZER.serialize(program) for program in value.programs],
        }

    def deserialize(self, value: object) -> WizardRegistry:
        decoded = self._decode(value)
        if not isinstance(decoded, dict) or set(decoded) != _REGISTRY_FIELDS:
            raise ValueError("Invalid Wizard registry")
        if type(decoded["version"]) is not int or decoded["version"] != WIZARD_REGISTRY_VERSION:
            raise ValueError("Invalid Wizard registry")
        if not isinstance(decoded["programs"], list):
            raise ValueError("Invalid Wizard registry")
        programs = tuple(WIZARD_PROGRAM_SERIALIZER.deserialize(program) for program in decoded["programs"])
        if len(programs) != len({program.id for program in programs}):
            raise ValueError("Invalid Wizard registry")
        return WizardRegistry(programs=programs)

    @staticmethod
    def _decode(value: object) -> object:
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid Wizard registry") from error


WIZARD_REGISTRY_SERIALIZER = WizardRegistrySerializer()
