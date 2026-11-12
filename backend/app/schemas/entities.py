from typing import Any

from pydantic import BaseModel, Field, field_validator


class MaxAttemptsBody(BaseModel):
    max_attempts: int = Field(ge=1, le=10)


class DependencyEdge(BaseModel):
    name: str = Field(min_length=1)
    kind: str = "hard"

    @field_validator("kind")
    @classmethod
    def _kind_is_valid(cls, value: str) -> str:
        if value not in ("hard", "soft"):
            raise ValueError("kind must be 'hard' or 'soft'")
        return value


class DependenciesBody(BaseModel):
    dependencies: list[DependencyEdge]


class EnabledBody(BaseModel):
    enabled: bool


class FixtureBody(BaseModel):
    fixture_path: str = Field(min_length=1)


class SettingBody(BaseModel):
    value: str


def as_plain_edges(dependencies: list[DependencyEdge]) -> list[dict[str, Any]]:
    return [edge.model_dump() for edge in dependencies]
