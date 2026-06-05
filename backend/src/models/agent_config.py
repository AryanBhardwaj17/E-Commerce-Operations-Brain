"""YAML agent config loader with Pydantic validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from core.settings import resolve_config_path


class ModelOverride(BaseModel):
    provider: str = "openai"
    model_id: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 4096
    fallback_model: str = "gpt-4o-mini"
    timeout_seconds: int = 60


class HandoffConfig(BaseModel):
    target: str
    condition: str


class AgentConfig(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    model: ModelOverride = Field(default_factory=ModelOverride)
    system_prompt: str
    tools_whitelist: list[str] = Field(default_factory=list)
    output_schema: str | None = None
    enforce_structured_output: bool = False
    human_approval_required_for: list[str] = Field(default_factory=list)
    max_tool_iterations: int = 5
    reflect_on_tool_use: bool = False
    max_context_tokens: int = 4096
    handoffs: list[HandoffConfig] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> AgentConfig:
        models_yaml = resolve_config_path("models.yaml")
        with open(models_yaml, encoding="utf-8") as f:
            models_raw = yaml.safe_load(f) or {}

        agent_name = Path(path).stem
        model_defaults = {
            **models_raw.get("defaults", {}),
            **models_raw.get("agents", {}).get(agent_name, {}),
        }

        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        data = raw.get("agent", raw)
        if "model" in data:
            data["model"] = {**model_defaults, **data["model"]}
        else:
            data["model"] = model_defaults

        return cls.model_validate(data)

    @property
    def requires_hitl(self) -> bool:
        return bool(self.human_approval_required_for)

    @property
    def hitl_tools(self) -> set[str]:
        if "*" in self.human_approval_required_for:
            return set(self.tools_whitelist)
        return set(self.human_approval_required_for)
