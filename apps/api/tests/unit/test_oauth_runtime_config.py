from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_api_compose_passes_google_oauth_credentials() -> None:
    compose = (ROOT / "infra/docker-compose.app.yml").read_text(encoding="utf-8")

    assert "PINVI_GOOGLE_OAUTH_CLIENT_ID: ${PINVI_GOOGLE_OAUTH_CLIENT_ID:-}" in compose
    assert "PINVI_GOOGLE_OAUTH_CLIENT_SECRET: ${PINVI_GOOGLE_OAUTH_CLIENT_SECRET:-}" in compose


def test_production_env_template_declares_google_oauth_credentials() -> None:
    env_template = (ROOT / "infra/.env.prod.example").read_text(encoding="utf-8")

    assert "PINVI_GOOGLE_OAUTH_CLIENT_ID=" in env_template
    assert "PINVI_GOOGLE_OAUTH_CLIENT_SECRET=" in env_template
