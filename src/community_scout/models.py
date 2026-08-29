from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class CommunityLead:
    source: str
    title: str
    summary: str
    repository_url: str
    community_url: str
    source_ref: str
    category: str = ""
    published_at: str | None = None
    captured_at: str = field(default_factory=utc_now)
    repository_mapping: Literal["explicit", "inferred", "missing"] = "explicit"

    @property
    def id(self) -> str:
        identity = "\n".join((self.source, self.repository_url, self.source_ref))
        return sha256(identity.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, **asdict(self)}
