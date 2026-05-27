"""Base dataclass for all domain models."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


@dataclass
class BaseModel:
    """Shared fields and helpers for every domain model."""

    id: Optional[int] = field(default=None)
    created_at: Optional[str] = field(default=None)
    updated_at: Optional[str] = field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict representation of this model."""
        return {k: v for k, v in asdict(self).items()}

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "BaseModel":
        """Construct an instance from a DB row dict.

        Subclasses should override this with typed construction.
        """
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})
