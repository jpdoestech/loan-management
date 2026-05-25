"""Base data model with common dict serialisation."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class BaseModel:
    """Abstract base for all domain models.

    Provides ``to_dict`` and ``from_dict`` convenience methods used by
    DAOs and GUI views.
    """

    def to_dict(self) -> Dict[str, Any]:
        """Serialise model fields to a plain dictionary.

        Returns:
            Dict mapping field names to values.
        """
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseModel":
        """Construct a model instance from a dictionary.

        Args:
            data: Dict whose keys correspond to dataclass fields.

        Returns:
            New model instance with fields populated from *data*.
        """
        field_names = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered)

    def __str__(self) -> str:  # noqa: D105
        return f"{self.__class__.__name__}({self.to_dict()})"
