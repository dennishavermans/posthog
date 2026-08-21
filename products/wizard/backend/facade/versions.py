import re

DEFAULT_WIZARD_VERSION = "2.60.0"
LEGACY_WIZARD_VERSION = "latest"
_EXACT_WIZARD_VERSION_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def is_exact_wizard_version(value: object) -> bool:
    return isinstance(value, str) and _EXACT_WIZARD_VERSION_PATTERN.fullmatch(value) is not None


def is_executable_wizard_version(value: object) -> bool:
    return value == LEGACY_WIZARD_VERSION or is_exact_wizard_version(value)
