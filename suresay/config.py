"""Settings from the environment. ``SURESAY_BACKEND=local`` runs with no AWS at all."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    backend: str = field(default_factory=lambda: _env("SURESAY_BACKEND", "local"))  # local | aws
    region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))
    data_dir: Path = field(default_factory=lambda: Path(_env("SURESAY_DATA_DIR", str(ROOT / "var"))))
    gate_table: str = field(default_factory=lambda: _env("SURESAY_GATE_TABLE", "suresay-gate"))
    state_table: str = field(default_factory=lambda: _env("SURESAY_STATE_TABLE", "suresay-state"))
    bucket: str = field(default_factory=lambda: _env("SURESAY_BUCKET"))
    asr: str = field(default_factory=lambda: _env("SURESAY_ASR", "auto"))  # auto | transcribe | nova-sonic | whisper | text
    whisper_model: str = field(default_factory=lambda: _env("SURESAY_WHISPER_MODEL", "small.en"))
    ranker: str = field(default_factory=lambda: _env("SURESAY_RANKER", "auto"))  # auto | nova | fuzzy
    nova_model_id: str = field(default_factory=lambda: _env("NOVA_MODEL_ID", "us.amazon.nova-2-lite-v1:0"))
    memory_id: str = field(default_factory=lambda: _env("AGENTCORE_MEMORY_ID"))
    agent_mode: str = field(default_factory=lambda: _env("SURESAY_AGENT_MODE", "auto"))  # auto | agent | direct
    agent_url: str = field(default_factory=lambda: _env("SURESAY_AGENT_URL", "http://127.0.0.1:8080/invocations"))
    agent_runtime_arn: str = field(default_factory=lambda: _env("AGENTCORE_RUNTIME_ARN"))
    agent_token: str = field(default_factory=lambda: _env("SURESAY_AGENT_TOKEN") or _local_token())
    default_user: str = field(default_factory=lambda: _env("SURESAY_DEFAULT_USER", "demo"))
    polly_voice: str = field(default_factory=lambda: _env("SURESAY_POLLY_VOICE", "Kajal"))
    polly_language: str = field(default_factory=lambda: _env("SURESAY_POLLY_LANGUAGE", "en-IN"))
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o for o in _env("SURESAY_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o)
    )
    evidence_language: str = field(default_factory=lambda: _env("SURESAY_EVIDENCE_LANGUAGE", "en-US"))  # hi-IN for Hindi
    # Who hears spoken answers on the cards: "" = the same recogniser as requests; "nova-sonic" = Amazon Nova 2 Sonic
    evidence_asr: str = field(default_factory=lambda: _env("SURESAY_EVIDENCE_ASR", ""))
    public_demo: bool = field(default_factory=lambda: _env("SURESAY_PUBLIC_DEMO") in ("1", "true", "yes"))
    # a live AI assistant driving SureSay over MCP from the user's own device ("" off, "nova-sonic": Amazon Nova 2 Sonic)
    live_agent: str = field(default_factory=lambda: _env("SURESAY_LIVE_AGENT"))
    carer_topic_arn: str = field(default_factory=lambda: _env("SURESAY_CARER_TOPIC_ARN"))
    learn: bool = field(default_factory=lambda: _env("SURESAY_LEARN", "1") not in ("0", "false", "no"))
    public_url: str = field(default_factory=lambda: _env("SURESAY_PUBLIC_URL"))  # "" = derive from the request
    oauth_clients: str = field(default_factory=lambda: _env("SURESAY_OAUTH_CLIENTS"))  # JSON, see suresay/oauth.py

    @property
    def is_aws(self) -> bool:
        return self.backend == "aws"


def _local_token() -> str:
    """A per-checkout agent token, so a fresh clone works without configuration."""
    path = ROOT / "var" / "agent_token"
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    path.write_text(token)
    path.chmod(0o600)
    return token


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()
