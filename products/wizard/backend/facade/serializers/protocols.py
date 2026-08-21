from typing import Protocol, TypeVar

T = TypeVar("T")


class DictSerializer(Protocol[T]):
    def serialize(self, value: T) -> dict[str, object]: ...

    def deserialize(self, value: object) -> T: ...
