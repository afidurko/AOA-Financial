"""LLM client used by every agent (local WASTE by default)."""

from aoa.llm.client import LLMClient, LLMError, llm_from_config

__all__ = ["LLMClient", "LLMError", "llm_from_config"]
