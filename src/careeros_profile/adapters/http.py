"""FastAPI adapter and composition root for the Profile Service."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine
from starlette.middleware.base import RequestResponseEndpoint

from careeros_profile.adapters.persistence import SqlAlchemyPersistenceProbe, create_profile_engine
from careeros_profile.application.operations import (
    PersistenceProbe,
    health_status,
    readiness_status,
)

CORRELATION_HEADER = "X-Correlation-ID"
LOGGER = logging.getLogger("careeros.profile.http")


class Settings(BaseSettings):
    """Validated startup configuration with redacted database credentials."""

    model_config = SettingsConfigDict(env_file=".env", extra="forbid", frozen=True)

    app_env: Literal["development", "test", "production"]
    log_level: Literal["debug", "info", "warning", "error"]
    database_url: SecretStr = Field(min_length=1)


class HealthResponse(BaseModel):
    """Public operational response without configuration details."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    status: Literal["ok", "ready", "unavailable"]
    service: Literal["profile-service"] = "profile-service"


def _correlation_id(request: Request) -> str:
    supplied = request.headers.get(CORRELATION_HEADER, "")
    if (
        supplied
        and len(supplied) <= 128
        and all(character.isalnum() or character in "-_." for character in supplied)
    ):
        return supplied
    return str(uuid4())


def create_app(
    settings: Settings | None = None,
    persistence_probe: PersistenceProbe | None = None,
) -> FastAPI:
    """Validate configuration and compose Profile Service adapters."""
    validated_settings = settings or Settings()
    LOGGER.setLevel(validated_settings.log_level.upper())
    engine: Engine | None = None
    probe = persistence_probe
    if probe is None:
        engine = create_profile_engine(validated_settings.database_url.get_secret_value())
        probe = SqlAlchemyPersistenceProbe(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            engine.dispose()

    application = FastAPI(
        title="CareerOS Profile Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def correlation_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = _correlation_id(request)
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        LOGGER.info(
            json.dumps(
                {
                    "correlation_id": correlation_id,
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return response

    @application.get("/health", response_model=HealthResponse, tags=["operations"])
    async def health() -> HealthResponse:
        return HealthResponse.model_validate(health_status())

    @application.get("/ready", response_model=HealthResponse, tags=["operations"])
    def ready(response: Response) -> HealthResponse:
        result = readiness_status(probe)
        if result.status == "unavailable":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse.model_validate(result)

    return application
