"""FastAPI adapter and composition root for the Profile Service."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    Security,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine
from starlette.middleware.base import RequestResponseEndpoint

from careeros_profile.adapters.auth import JwtTokenVerifier, SigningKeyResolver
from careeros_profile.adapters.migrations.runner import AlembicMigrationRunner
from careeros_profile.adapters.persistence.sqlalchemy import (
    SqlAlchemyExperienceRepository,
    SqlAlchemyPersistenceProbe,
    create_profile_engine,
)
from careeros_profile.application.ports.authentication import (
    AccountContext,
    TokenValidationError,
    TokenVerifier,
)
from careeros_profile.application.ports.persistence import MigrationRunner, PersistenceProbe
from careeros_profile.application.ports.profile import ExperienceRepository, ProfileOwner
from careeros_profile.application.use_cases.experiences import (
    InvalidCursor,
    ManageExperiences,
    ProfileItemNotFound,
)
from careeros_profile.application.use_cases.operations import (
    GetHealth,
    GetReadiness,
    StartApplication,
)
from careeros_profile.domain.experience import Experience, ExperienceDraft

CORRELATION_HEADER = "X-Correlation-ID"
LOGGER = logging.getLogger("careeros.profile.http")
BEARER = HTTPBearer(auto_error=False)


class Settings(BaseSettings):
    """Validated startup configuration with redacted database credentials."""

    model_config = SettingsConfigDict(env_file=".env", extra="forbid", frozen=True)

    app_env: Literal["development", "test", "production"]
    log_level: Literal["debug", "info", "warning", "error"]
    database_url: SecretStr = Field(min_length=1)
    oidc_issuer: AnyHttpUrl
    oidc_audience: str = Field(min_length=1)
    oidc_jwks_url: AnyHttpUrl


class HealthResponse(BaseModel):
    """Public operational response without configuration details."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    status: Literal["ok", "ready", "unavailable"]
    service: Literal["profile-service"] = "profile-service"


class PageMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    next_cursor: str | None = Field(default=None, serialization_alias="nextCursor")


class ExperiencePageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[Experience, ...]
    page: PageMetadata


class Problem(BaseModel):
    """RFC 9457-compatible response without validation internals."""

    model_config = ConfigDict(frozen=True)

    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    correlation_id: str = Field(serialization_alias="correlationId")


def _correlation_id(request: Request) -> str:
    supplied = request.headers.get(CORRELATION_HEADER, "")
    if (
        supplied
        and len(supplied) <= 128
        and all(character.isalnum() or character in "-_." for character in supplied)
    ):
        return supplied
    return str(uuid4())


def _problem(request: Request, status_code: int, code: str, title: str, detail: str) -> Problem:
    return Problem(
        type=f"https://api.careeros.invalid/problems/{code.lower().replace('_', '-')}",
        title=title,
        status=status_code,
        detail=detail,
        instance=f"https://api.careeros.invalid{request.url.path}",
        code=code,
        correlation_id=request.state.correlation_id,
    )


def _http_error(status_code: int, code: str, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "title": title, "detail": detail},
    )


def require_account_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(BEARER)],
) -> AccountContext:
    """Validate a bearer token and expose normalized identity."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _http_error(
            401, "UNAUTHENTICATED", "Unauthenticated", "A valid bearer token is required."
        )
    verifier = cast(TokenVerifier, request.app.state.token_verifier)
    try:
        return verifier.verify(credentials.credentials)
    except TokenValidationError:
        raise _http_error(
            401, "UNAUTHENTICATED", "Unauthenticated", "A valid bearer token is required."
        ) from None


def _require_scope(context: AccountContext, scope: str) -> ProfileOwner:
    if scope not in context.scopes:
        raise _http_error(403, "FORBIDDEN", "Forbidden", "The required profile scope is missing.")
    return ProfileOwner(account_id=context.account_id, tenant_id=context.tenant_id)


def create_app(
    settings: Settings | None = None,
    persistence_probe: PersistenceProbe | None = None,
    migration_runner: MigrationRunner | None = None,
    token_verifier: TokenVerifier | None = None,
    experience_repository: ExperienceRepository | None = None,
) -> FastAPI:
    """Compose concrete adapters and inject ports into application use cases."""
    validated_settings = settings or Settings()
    LOGGER.setLevel(validated_settings.log_level.upper())
    database_url = validated_settings.database_url.get_secret_value()
    engine: Engine | None = None
    if persistence_probe is None or experience_repository is None:
        engine = create_profile_engine(database_url)
    probe = persistence_probe or SqlAlchemyPersistenceProbe(cast(Engine, engine))
    repository = experience_repository or SqlAlchemyExperienceRepository(cast(Engine, engine))
    migrations = migration_runner or AlembicMigrationRunner(database_url)
    get_health = GetHealth()
    get_readiness = GetReadiness(probe)
    start_application = StartApplication(migrations)
    experiences = ManageExperiences(repository)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        start_application.execute()
        yield
        if engine is not None:
            engine.dispose()

    application = FastAPI(
        title="CareerOS Profile Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.token_verifier = token_verifier or JwtTokenVerifier(
        resolver=SigningKeyResolver(str(validated_settings.oidc_jwks_url)),
        issuer=str(validated_settings.oidc_issuer),
        audience=validated_settings.oidc_audience,
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

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, error: HTTPException) -> JSONResponse:
        details: dict[str, object] = error.detail if isinstance(error.detail, dict) else {}
        problem = _problem(
            request,
            error.status_code,
            str(details.get("code", "REQUEST_FAILED")),
            str(details.get("title", "Request failed")),
            str(details.get("detail", "The request could not be completed.")),
        )
        headers = dict(error.headers or {})
        if error.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            problem.model_dump(by_alias=True),
            status_code=error.status_code,
            media_type="application/problem+json",
            headers=headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, _: RequestValidationError
    ) -> JSONResponse:
        problem = _problem(
            request,
            422,
            "VALIDATION_FAILED",
            "Validation failed",
            "The request does not satisfy the profile contract.",
        )
        return JSONResponse(
            problem.model_dump(by_alias=True),
            status_code=422,
            media_type="application/problem+json",
        )

    @application.get("/health", response_model=HealthResponse, tags=["operations"])
    async def health() -> HealthResponse:
        return HealthResponse.model_validate(get_health.execute())

    @application.get("/ready", response_model=HealthResponse, tags=["operations"])
    def ready(response: Response) -> HealthResponse:
        result = get_readiness.execute()
        if result.status == "unavailable":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse.model_validate(result)

    Account = Annotated[AccountContext, Depends(require_account_context)]

    @application.get(
        "/v1/profile/items",
        response_model=ExperiencePageResponse,
        response_model_exclude_none=True,
        tags=["Profile items"],
    )
    def list_items(
        account: Account,
        kind: Literal["experience", "education", "skill"] | None = None,
        page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
        cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    ) -> ExperiencePageResponse:
        owner = _require_scope(account, "profile:read")
        if kind not in (None, "experience"):
            return ExperiencePageResponse(items=(), page=PageMetadata())
        try:
            result = experiences.list(owner, page_size=page_size, cursor=cursor)
        except InvalidCursor:
            raise _http_error(
                422, "VALIDATION_FAILED", "Validation failed", "Invalid cursor."
            ) from None
        return ExperiencePageResponse(
            items=result.items,
            page=PageMetadata(next_cursor=result.next_cursor),
        )

    @application.post(
        "/v1/profile/items",
        response_model=Experience,
        response_model_exclude_none=True,
        status_code=201,
        tags=["Profile items"],
    )
    def create_item(draft: ExperienceDraft, account: Account, response: Response) -> Experience:
        owner = _require_scope(account, "profile:write")
        item = experiences.create(owner, draft)
        response.headers["Location"] = f"/v1/profile/items/{item.item_id}"
        return item

    @application.get(
        "/v1/profile/items/{itemId}",
        response_model=Experience,
        response_model_exclude_none=True,
        tags=["Profile items"],
    )
    def get_item(item_id: Annotated[UUID, Path(alias="itemId")], account: Account) -> Experience:
        owner = _require_scope(account, "profile:read")
        try:
            return experiences.get(owner, item_id)
        except ProfileItemNotFound:
            raise _http_error(404, "NOT_FOUND", "Not found", "Profile item not found.") from None

    @application.put(
        "/v1/profile/items/{itemId}",
        response_model=Experience,
        response_model_exclude_none=True,
        tags=["Profile items"],
    )
    def replace_item(
        item_id: Annotated[UUID, Path(alias="itemId")], draft: ExperienceDraft, account: Account
    ) -> Experience:
        owner = _require_scope(account, "profile:write")
        try:
            return experiences.replace(owner, item_id, draft)
        except ProfileItemNotFound:
            raise _http_error(404, "NOT_FOUND", "Not found", "Profile item not found.") from None

    @application.delete(
        "/v1/profile/items/{itemId}",
        status_code=204,
        tags=["Profile items"],
    )
    def delete_item(item_id: Annotated[UUID, Path(alias="itemId")], account: Account) -> Response:
        owner = _require_scope(account, "profile:write")
        try:
            experiences.delete(owner, item_id)
        except ProfileItemNotFound:
            raise _http_error(404, "NOT_FOUND", "Not found", "Profile item not found.") from None
        return Response(status_code=204)

    return application
