"""Configurarea aplicației. Valorile vin din mediu sau din `.env`; nicio cheie în cod."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM: Claude pe Amazon Bedrock prin endpoint-ul Mantle
    aws_region: str = "us-east-1"  # pasul 0: în UE, SCP-ul contului de hackathon blochează Mantle
    versoml_llm_mode: Literal["auto", "live", "replay", "offline"] = "auto"
    model_opus: str = "anthropic.claude-opus-5-5"
    model_sonnet: str = "anthropic.claude-sonnet-5"  # Sonnet 5.5 nu e activat pe cont
    model_haiku: str = "anthropic.claude-haiku-4-5"  # Haiku 5.5 nu e activat pe cont
    model_fallbacks: str = "anthropic.claude-opus-4-8,anthropic.claude-sonnet-5,anthropic.claude-haiku-4-5"

    # OSINT: "fixture" = doar înregistrări locale, "live" = doar surse reale, "auto" = live cu rezervă
    versoml_osint_mode: Literal["fixture", "live", "auto"] = "auto"
    serper_api_key: SecretStr | None = None
    brave_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    exa_api_key: SecretStr | None = None
    jina_api_key: SecretStr | None = None
    urlscan_api_key: SecretStr | None = None
    virustotal_api_key: SecretStr | None = None
    urlhaus_auth_key: SecretStr | None = None
    google_safe_browsing_key: SecretStr | None = None

    # Procese și porturi: fiecare zonă rulează separat
    versoml_host: str = "127.0.0.1"
    versoml_client_port: int = 8000
    versoml_aml_port: int = 8001
    # URL-urile prin care zonele se văd între ele (în docker: http://client:8000, http://aml:8001)
    versoml_client_url: str | None = None
    versoml_aml_url: str | None = None
    # Fallback when Bedrock is throttled or down: the Claude API, with a key from console.anthropic.com
    # (ANTHROPIC_API_KEY in .env or in the environment; never committed)
    anthropic_api_key: SecretStr | None = None

    # Public access (the demo tunnel) and the limits that keep it inside the Bedrock quota
    versoml_public_hosts: str = "footpad-outpour-overrule.ngrok-free.dev"
    versoml_public_site: str = "https://versoml.vercel.app"  # the seal's QR code opens /verify/<case> here
    versoml_llm_max_concurrency: int = 6
    versoml_case_runs_per_caller: int = 5  # per 10 minutes
    versoml_case_runs_per_hour: int = 40  # every entry point together
    versoml_kb_asks_per_caller: int = 10  # per 10 minutes
    versoml_kb_asks_per_hour: int = 120
    versoml_mcp_calls_per_caller: int = 60  # per minute

    # Secretul comun doar pentru dioda de date (generat la prima rulare dacă lipsește)
    versoml_diode_secret: SecretStr | None = None

    # Operator sessions: who signs a decision or changes a rule parameter (never the request body).
    # "demo" gives each console a named demo operator, and every signature made with one says so in the ledger;
    # "strict" accepts only sessions the bank's sign-in issues with the same secret. The secret signs sessions and
    # approval tokens; when it is unset, each process draws a random one (a restart signs everyone out).
    versoml_operator_mode: Literal["demo", "strict"] = "demo"
    versoml_operator_secret: SecretStr | None = None
    versoml_session_hours: float = 4.0

    # Zona procesului curent: un proces de zonă nu poate deschide baza celeilalte zone (stratul 1 al zidului)
    versoml_zone: Literal["client", "aml", "all"] = "all"

    # Directoare
    versoml_var_dir: Path = ROOT / "var"

    @property
    def var_dir(self) -> Path:
        self.versoml_var_dir.mkdir(parents=True, exist_ok=True)
        return self.versoml_var_dir

    @property
    def client_db(self) -> Path:
        if self.versoml_zone == "aml":
            raise PermissionError("The wall: the AML zone process has no access to the client zone database.")
        return self.var_dir / "client_zone.db"

    @property
    def aml_db(self) -> Path:
        if self.versoml_zone == "client":
            raise PermissionError("The wall: the client zone process has no access to the AML zone database.")
        return self.var_dir / "aml_zone.db"

    @property
    def keys_dir(self) -> Path:
        path = self.var_dir / "keys"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def models_dir(self) -> Path:
        path = self.var_dir / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def replay_dir(self) -> Path:
        """Committed LLM recordings for replay mode (in git, so the demo works without network). Read only."""
        path = PACKAGE_DIR / "data" / "replay"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def replay_record_path(self) -> Path:
        """Where live runs append new recordings: var/replay/replay.jsonl (var/ is outside git)."""
        path = self.var_dir / "replay"
        path.mkdir(parents=True, exist_ok=True)
        return path / "replay.jsonl"

    @property
    def client_url(self) -> str:
        host = "127.0.0.1" if self.versoml_host in ("0.0.0.0", "") else self.versoml_host
        return (self.versoml_client_url or f"http://{host}:{self.versoml_client_port}").rstrip("/")

    @property
    def aml_url(self) -> str:
        host = "127.0.0.1" if self.versoml_host in ("0.0.0.0", "") else self.versoml_host
        return (self.versoml_aml_url or f"http://{host}:{self.versoml_aml_port}").rstrip("/")

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.model_fallbacks.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    from versoml.secrets import register_secret  # import târziu: secrets importă config

    # orice cheie din .env (Serper, Brave, urlscan…) e înlocuită cu *** în loguri și trasări
    for name in Settings.model_fields:
        value = getattr(settings, name)
        if isinstance(value, SecretStr):
            register_secret(value.get_secret_value())
    return settings
