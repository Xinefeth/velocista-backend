"""Configuración leída del entorno (o de un .env en local)."""

from urllib.parse import quote

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    sim_enabled: bool = False
    sim_ws_url: str = "wss://velocista-sim-production.up.railway.app/ws"
    sim_robot_id: str | None = None
    sim_track_id: str | None = None
    sim_internal_robot_id: str | None = None
    sim_setup_id: int | None = Field(default=None, ge=1)
    sim_profile_id: str | None = None
    sim_store_telemetry: bool = True
    # Se guarda 1 de cada N frames (50 Hz / 5 = 10 Hz); la consola en vivo sigue viendo todos.
    sim_telemetry_stride: int = Field(default=5, ge=1, le=100)
    sim_max_telemetry_rows_per_run: int = Field(default=20000, ge=1)
    sim_queue_size: int = Field(default=5000, ge=32, le=100000)
    sim_command_timeout: float = Field(default=10, gt=0, le=120)
    sim_reconnect_max_seconds: float = Field(default=30, ge=1, le=300)

    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me"
    auth_required: bool = False
    admin_username: str = "admin"
    admin_password: str = ""
    simulation_service_token: str = ""
    token_expire_minutes: int = Field(default=60, ge=1, le=1440)

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.app_env == "production":
            if not self.auth_required:
                raise ValueError("AUTH_REQUIRED must be enabled in production")
            if (
                len(self.secret_key) < 32
                or len(self.admin_password) < 12
                or len(self.simulation_service_token) < 32
            ):
                raise ValueError(
                    "Configure SECRET_KEY and SIMULATION_SERVICE_TOKEN (32+ chars), "
                    "and ADMIN_PASSWORD (12+ chars)"
                )
            for token in (self.device_token_robot, self.device_token_timer):
                if len(token) < 24 or token.startswith("dev-token-"):
                    raise ValueError("Configure unique DEVICE_TOKEN_ROBOT/TIMER (24+ chars)")
            if self.device_token_robot == self.device_token_timer:
                raise ValueError("Device tokens must be different")
            if "*" in self.cors_list:
                raise ValueError("Configure exact frontend origins instead of wildcard CORS")
        return self

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # En la nube (Render, Railway, …) la base llega en una sola variable DATABASE_URL.
    # Si está presente, tiene prioridad sobre las POSTGRES_* (uso local con Docker).
    external_database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")

    postgres_user: str = "velocista"
    postgres_password: str = "change-this-password"
    postgres_db: str = "velocista"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 15432

    # Tokens por dispositivo para autenticar las conexiones WS.
    device_token_robot: str = "dev-token-robot"
    device_token_timer: str = "dev-token-timer"

    @staticmethod
    def _with_psycopg_driver(url: str) -> str:
        """Normaliza el esquema al driver psycopg 3 que usan el motor y Alembic.

        Render entrega `postgres://` o `postgresql://`; SQLAlchemy necesita
        `postgresql+psycopg://` para elegir psycopg 3 explícitamente.
        """
        for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
            if url.startswith(prefix):
                return url
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://") :]
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://") :]
        return url

    @property
    def database_url(self) -> str:
        if self.external_database_url:
            return self._with_psycopg_driver(self.external_database_url)
        return (
            "postgresql+psycopg://"
            f"{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
