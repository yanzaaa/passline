"""Tests for the QC agent configuration."""
from __future__ import annotations

import pytest

from passline.agents.qc_agent import build_qc_agent, _DEFAULT_MODEL


class TestQcAgentModel:
    def test_default_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without PASSLINE_QC_MODEL set, agent uses the default fallback."""
        monkeypatch.delenv("PASSLINE_QC_MODEL", raising=False)
        agent = build_qc_agent()
        assert agent.model == _DEFAULT_MODEL

    def test_env_var_overrides_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PASSLINE_QC_MODEL env var is respected."""
        monkeypatch.setenv("PASSLINE_QC_MODEL", "gemini-3-flash-preview")
        agent = build_qc_agent()
        assert agent.model == "gemini-3-flash-preview"

    def test_pro_preview_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Pro preview model can be selected via env var."""
        monkeypatch.setenv("PASSLINE_QC_MODEL", "gemini-3.1-pro-preview")
        agent = build_qc_agent()
        assert agent.model == "gemini-3.1-pro-preview"

    def test_agent_name_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Agent name is always 'qc_agent' regardless of model env var."""
        monkeypatch.setenv("PASSLINE_QC_MODEL", "gemini-3-flash-preview")
        agent = build_qc_agent()
        assert agent.name == "qc_agent"
