"""환경변수 + 설정 (pydantic-settings).

루트 `.env.example` 항목과 동기.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Literal, Self, cast
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PinviEnvironment = Literal["development", "test", "smoke", "staging", "production"]
_SERVICE_PROVENANCE_FILENAME = "kor-travel-map-service-provenance-v1.json"
_PACKAGED_SERVICE_PROVENANCE_PATH = f"_contract_data/{_SERVICE_PROVENANCE_FILENAME}"


def _service_provenance_text() -> str:
    packaged = files("app").joinpath(_PACKAGED_SERVICE_PROVENANCE_PATH)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")

    for directory in Path(__file__).resolve().parents:
        candidate = directory / "contracts" / _SERVICE_PROVENANCE_FILENAME
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise RuntimeError(f"Map service provenance file is missing: {_SERVICE_PROVENANCE_FILENAME}")


def _required_string(payload: dict[str, object], field: str, pattern: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise RuntimeError(f"Map service provenance {field} is invalid")
    return value


def _capability_generation(capabilities: dict[str, object], name: str) -> int:
    capability = capabilities.get(name)
    if not isinstance(capability, dict):
        raise RuntimeError(f"Map service provenance capability {name} is missing")
    generation = capability.get("generation")
    if type(generation) is not int or generation < 1:
        raise RuntimeError(f"Map service provenance capability {name} generation is invalid")
    return generation


def _load_service_provenance() -> tuple[str, str, int, int, int]:
    raw = json.loads(_service_provenance_text())
    if not isinstance(raw, dict):
        raise RuntimeError("Map service provenance must be an object")
    payload = cast(dict[str, object], raw)
    if set(payload) != {
        "capabilities",
        "map_release_revision",
        "service_openapi_sha256",
        "version",
    }:
        raise RuntimeError("Map service provenance fields are invalid")
    if payload["version"] != 1:
        raise RuntimeError("Map service provenance version is unsupported")
    capabilities_value = payload["capabilities"]
    if not isinstance(capabilities_value, dict):
        raise RuntimeError("Map service provenance capabilities are invalid")
    capabilities = cast(dict[str, object], capabilities_value)
    if set(capabilities) != {"cache_target", "c6c_cancel_probe", "curation_snapshot"}:
        raise RuntimeError("Map service provenance capability inventory is invalid")
    return (
        _required_string(payload, "service_openapi_sha256", r"[0-9a-f]{64}"),
        _required_string(payload, "map_release_revision", r"[0-9a-f]{40}"),
        _capability_generation(capabilities, "cache_target"),
        _capability_generation(capabilities, "c6c_cancel_probe"),
        _capability_generation(capabilities, "curation_snapshot"),
    )


(
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
    KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_C6C_CANCEL_PROBE_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_CURATION_SNAPSHOT_CAPABILITY_GENERATION,
) = _load_service_provenance()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 환경
    pinvi_environment: PinviEnvironment = "development"

    # Database
    pinvi_database_url: str = Field(
        default="postgresql+asyncpg://pinvi:pinvi_dev_password@localhost:5432/pinvi"
    )
    pinvi_database_pool_size: int = 10

    # JWT / 세션
    pinvi_jwt_secret_key: str = Field(default="pinvi-local-jwt-secret-change-me", min_length=32)
    pinvi_access_token_minutes: int = 10
    pinvi_refresh_token_days: int = 7
    pinvi_admin_session_ttl: int = 3600
    pinvi_mcp_jwt_secret: str = Field(default="pinvi-local-mcp-secret-change-me", min_length=32)
    pinvi_mcp_token_default_days: int = 30
    pinvi_mcp_rate_limit_per_minute: int = 60

    # Resend
    pinvi_resend_api_key: str = ""
    pinvi_resend_api_base_url: str = "https://api.resend.com"
    pinvi_resend_from_email: str = "Pinvi <noreply@send.pinvi.local>"
    pinvi_resend_timeout_seconds: int = 5
    pinvi_resend_webhook_secret: str = ""
    pinvi_resend_webhook_allow_unsigned: bool = False
    pinvi_email_outbox_worker_enabled: bool = True
    pinvi_email_outbox_drain_interval_seconds: float = 5.0
    pinvi_email_outbox_batch_size: int = 50
    # 미인증 로그인/재발송 요청 시 가입 인증 메일 재발송 최소 간격(초). 같은 사용자 중복 발송 방지.
    pinvi_email_verification_resend_cooldown_seconds: int = 60
    pinvi_web_base_url: str = "http://localhost:12805"
    pinvi_dagster_base_url: str = "http://localhost:12802"
    pinvi_email_verification_path: str = "/verify-email"
    pinvi_auth_reset_path: str = Field(
        default="/reset-password",
        validation_alias="PINVI_PASSWORD_RESET_PATH",
    )

    # OAuth (Sprint 2부터 실제 사용)
    pinvi_google_oauth_client_id: str = ""
    pinvi_google_oauth_client_secret: str = ""
    pinvi_naver_oauth_client_id: str = ""
    pinvi_naver_oauth_client_secret: str = ""
    pinvi_kakao_oauth_rest_api_key: str = ""
    pinvi_kakao_oauth_client_secret: str = ""
    pinvi_oauth_callback_base_url: str = "http://localhost:12801"

    # 외부 장소 provider(표시 전용, ADR-054 / docs/integrations/kakao-naver-local.md)
    # Kakao Local은 기존 OAuth REST 키(pinvi_kakao_oauth_rest_api_key)를 재사용한다(신규 키 없음).
    pinvi_kakao_local_enabled: bool = True
    pinvi_kakao_local_base_url: str = "https://dapi.kakao.com"
    # Naver Local은 OAuth 로그인용과 다른 검색 API 전용 앱 credential(SecretStr).
    pinvi_naver_local_enabled: bool = True
    pinvi_naver_local_base_url: str = "https://openapi.naver.com"
    pinvi_naver_search_client_id: SecretStr = SecretStr("")
    pinvi_naver_search_client_secret: SecretStr = SecretStr("")
    # 공통 전송/보강 정책
    pinvi_place_provider_timeout_seconds: float = 2.5
    pinvi_place_provider_max_attempts: int = 2
    # K: 내부 결과(feature+my_poi+address)가 이 수 미만일 때만 Kakao/Naver를 호출한다.
    pinvi_place_search_internal_threshold: int = 5
    pinvi_place_search_cache_ttl_seconds: int = 60
    pinvi_oauth_state_ttl_seconds: int = 600
    pinvi_oauth_http_timeout_seconds: int = 5
    # 모바일 OAuth: callback이 이 앱 딥링크로 1회용 code를 실어 리다이렉트한다(ADR-044/032).
    pinvi_mobile_oauth_redirect: str = "pinvi://oauth"
    pinvi_mobile_oauth_exchange_ttl_seconds: int = 120

    # RustFS (S3 호환 객체 저장소)
    pinvi_rustfs_endpoint_url: str = "http://localhost:12101"
    pinvi_rustfs_public_endpoint_url: str = "http://127.0.0.1:12101"
    pinvi_rustfs_bucket: str = "pinvi-media"
    pinvi_rustfs_access_key_id: str = "rustfsadmin"
    pinvi_rustfs_secret_access_key: str = "rustfsadmin"  # noqa: S105 - 로컬 dev 기본값
    pinvi_rustfs_presigned_url_expires_seconds: int = 900
    pinvi_rustfs_max_upload_bytes: int = 10_485_760
    pinvi_rustfs_allowed_content_types: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
            "video/mp4",
            "application/pdf",
        ]
    )
    pinvi_rustfs_public_base_url: str = ""
    # Trip/POI 첨부 개수 상한(남용 방지, T-105)
    pinvi_max_attachments_per_target: int = 30

    # kor-travel-map 독립 프로그램 (지도 feature OpenAPI HTTP, ADR-026/027)
    # `docs/integrations/kor-travel-map-rest-api.md` §1 — 전 표면 API/Admin API :12701.
    pinvi_kor_travel_map_api_base_url: str = "http://localhost:12701"
    # admin feature change(`/v1/admin/features*`, T-180)도 같은 호스트 :12701.
    pinvi_kor_travel_map_admin_base_url: str = "http://localhost:12701"
    # 인증은 인프라 계층(reverse proxy / IP allowlist). 설정 시 X-Kor-Travel-Map-Service-Token 전달.
    pinvi_kor_travel_map_service_token: str = ""
    # public REST의 X-Kor-Travel-Map-Api-Key header. 미설정 시 PINVI_VWORLD_API_KEY 사용.
    pinvi_kor_travel_map_public_api_key: str = ""
    # admin-path 전용 서비스 토큰(미설정 시 공용 service token fallback).
    # §7 확정(kor_travel_map T-217c): 운영 인증은 인프라 계층(SSO/IP allowlist) — token은 선택 pass-through.
    pinvi_kor_travel_map_admin_service_token: str = ""
    # kor-travel-map ADR-060: admin proxy gate가 켜진 운영 API에는 secret + actor 헤더가 필요.
    pinvi_kor_travel_map_admin_proxy_secret: str = ""
    pinvi_kor_travel_map_admin_actor: str = "pinvi-admin"
    # canonical /v1/ops/datasets*·/v1/ops/pipeline* 전용 server principal.
    # read/cancel 자격을 분리하고 요청 actor 대신 map 서버의 고정 actor를 사용한다.
    pinvi_kor_travel_map_ops_read_token: SecretStr | None = None
    pinvi_kor_travel_map_ops_cancel_token: SecretStr | None = None
    # canonical curation collection/item snapshot read 전용 exact-scope credential.
    # admin/service/cache-target token으로 fallback하지 않는다.
    pinvi_kor_travel_map_curation_snapshot_token: SecretStr | None = None
    # T-VN-40C maintenance fence에서 legacy identity→canonical UUID mapping만 읽는 별도 principal.
    # snapshot read token과 공유하면 Map이 403으로 fail-close한다.
    pinvi_kor_travel_map_curation_cutover_mapping_token: SecretStr | None = None
    pinvi_kor_travel_map_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        allow_inf_nan=False,
    )
    pinvi_kor_travel_map_max_attempts: int = 3
    pinvi_kor_travel_map_batch_chunk_size: int = Field(
        default=200,
        ge=1,
        le=200,
    )  # /v1/features/batch cap

    # cache target generation/outbox paired worker (ADR-058). false여도 DB projection은 계속된다.
    pinvi_kor_travel_map_cache_target_sync_enabled: bool = False
    pinvi_kor_travel_map_cache_target_command_token: SecretStr | None = None
    pinvi_kor_travel_map_cache_target_consumer_token: SecretStr | None = None
    # restore/recovery job 전용이며 ordinary API runtime에는 주입하지 않는다.
    pinvi_kor_travel_map_cache_target_restore_fence_token: SecretStr | None = None
    pinvi_kor_travel_map_cache_target_recovery_token: SecretStr | None = None
    pinvi_kor_travel_map_cache_target_consumer_id: str = Field(
        default="pinvi-cache-target-consumer", min_length=1, max_length=64
    )
    pinvi_kor_travel_map_cache_target_batch_size: int = Field(default=100, ge=1, le=500)
    pinvi_kor_travel_map_cache_target_lease_seconds: int = Field(default=60, ge=10, le=300)
    pinvi_kor_travel_map_cache_target_poll_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=60,
        allow_inf_nan=False,
    )
    pinvi_kor_travel_map_cache_target_max_attempts: int = Field(default=5, ge=1, le=20)
    # paired OpenAPI가 확정될 때 배포 manifest가 exact 값을 넣는다. source revision은 vendored artifact
    # owner provenance이며 배포 이미지/Map /version revision이 아니다. 빈 값으로 enable할 수 없다.
    pinvi_kor_travel_map_cache_target_expected_openapi_sha256: str = ""
    pinvi_kor_travel_map_cache_target_expected_source_revision: str = ""
    pinvi_kor_travel_map_cache_target_expected_contract_generation: int | None = Field(
        default=None, gt=0
    )

    # kor-travel-geo v2 REST (geocoding/주소/행정구역, ADR-025) — `docs/integrations/kor-travel-geo.md`.
    pinvi_kor_travel_geo_base_url: str = "http://localhost:12501"
    pinvi_kor_travel_geo_timeout_seconds: float = 5.0
    pinvi_kor_travel_geo_max_attempts: int = 3

    # VWorld 지도 키 (ADR-043/048) — 웹은 빌드타임 NEXT_PUBLIC_VWORLD_API_KEY를 쓰지만,
    # 모바일 앱(`apps/mobile`)은 키를 번들하지 않고 GET /mobile/vworld/token 으로 인증 후
    # server-issued 키를 발급받는다(키 미설정 시 endpoint는 503). 같은 값이 kor-travel-geo
    # v2 REST의 공개 API `key` query로도 쓰이며, 별도 geo API key 설정은 두지 않는다.
    pinvi_vworld_api_key: str = ""
    pinvi_vworld_token_ttl_seconds: int = 600

    # Telegram Bot 알림 (T-106) — `docs/integrations/telegram.md`.
    # bot token 원본은 DB 저장 X(§1), 로그는 mask_token으로만(§9).
    pinvi_telegram_api_base: str = "https://api.telegram.org"
    pinvi_telegram_timeout_seconds: float = 5.0
    pinvi_telegram_bot_token_default: str = ""  # 시스템/Admin 봇
    pinvi_telegram_admin_chat_id: str = ""
    # outbox drain worker (§8)
    pinvi_telegram_outbox_worker_enabled: bool = True
    pinvi_telegram_outbox_drain_interval_seconds: float = 5.0
    pinvi_telegram_outbox_batch_size: int = 50

    # 위치 감사 async outbox drain worker (T-146 / D-20)
    pinvi_location_audit_outbox_worker_enabled: bool = True
    pinvi_location_audit_outbox_drain_interval_seconds: float = 1.0
    pinvi_location_audit_outbox_batch_size: int = 200

    # Retention execution kill-switch (T-276). Dry-run은 항상 허용, execute는 운영에서 명시적으로 연다.
    pinvi_retention_execute_enabled: bool = False
    pinvi_retention_execute_confirm_phrase: str = "EXECUTE RETENTION"

    # Feature 조회 process-local TTL 캐시 (T-146 / D-26)
    pinvi_feature_cache_enabled: bool = True
    pinvi_feature_cache_ttl_seconds: float = 60.0
    pinvi_feature_cache_max_size: int = 10000

    # CORS
    pinvi_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:12805", "http://127.0.0.1:12805"]
    )

    # Geofencing (ADR-018) — 기본은 비활성, 운영에서 3차 fallback으로 활성.
    pinvi_geofence_enabled: bool = False
    pinvi_geofence_allowed_countries: list[str] = Field(default_factory=lambda: ["KR"])
    pinvi_geofence_country_header: str = "CF-IPCountry"
    pinvi_geofence_trusted_proxy_header: str = "X-Pinvi-Geofence-Proxy"
    pinvi_geofence_trusted_proxy_secret: str = ""
    pinvi_geofence_trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    pinvi_geofence_mtls_verified_header: str = ""
    pinvi_geofence_mtls_verified_value: str = "SUCCESS"
    pinvi_geofence_block_unknown: bool = False
    pinvi_geofence_bypass_paths: list[str] = Field(
        default_factory=lambda: [
            "/health",
            "/health/db",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
    )

    # HTTP rate limit (ADR-038 / T-195). backend=auto uses Postgres in production/staging
    # and process-local memory in development/test/smoke.
    pinvi_rate_limit_enabled: bool = True
    pinvi_rate_limit_backend: str = "auto"  # auto | memory | postgres
    pinvi_rate_limit_fail_open: bool = False
    pinvi_rate_limit_window_seconds: int = 60
    pinvi_rate_limit_public_per_minute: int = 60
    pinvi_rate_limit_authenticated_per_minute: int = 60
    pinvi_rate_limit_auth_per_minute: int = 5
    pinvi_rate_limit_oauth_per_minute: int = 10
    pinvi_rate_limit_storage_upload_per_minute: int = 30
    pinvi_rate_limit_feature_search_per_minute: int = 60
    pinvi_rate_limit_trip_export_per_minute: int = 20
    pinvi_rate_limit_shared_token_per_minute: int = 60
    pinvi_rate_limit_body_peek_max_bytes: int = 65_536
    pinvi_rate_limit_client_ip_header: str = ""
    pinvi_rate_limit_bypass_paths: list[str] = Field(
        default_factory=lambda: [
            "/health",
            "/health/db",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
    )

    # WebSocket safety guard (ADR-035)
    pinvi_ws_client_rate_per_second: int = 5
    pinvi_ws_client_rate_per_minute: int = 60
    pinvi_ws_rate_limit_close_grace_seconds: float = 30.0
    pinvi_ws_max_connections_per_trip: int = 10
    pinvi_ws_max_connections_total: int = 200
    pinvi_ws_send_timeout_seconds: float = 2.0
    # handshake-time reject(accept→close) 사이 settle. 101 upgrade를 별도 backend write로
    # flush해 close code가 리버스 프록시 edge를 건너 살아남게 한다(미적용 시 브라우저가
    # 4401/4403 등 대신 1006을 관측 — kor-travel-map C7 #809/#820과 동일 계층 문제). 0..5s.
    pinvi_ws_handshake_close_settle_seconds: float = 0.25
    # settle은 accept 이후(cap/rate-limit 이전) 소켓을 잠깐 붙잡으므로, 미인증 reject flood가
    # settle로 FD를 증폭하지 못하게 동시 settle 수를 cap한다(초과분은 settle 없이 즉시 닫음).
    # 0이면 무제한. 정상 reject는 저volume이라 항상 cap 안에 든다.
    pinvi_ws_max_concurrent_reject_settles: int = 64

    # Sentry
    pinvi_sentry_dsn: str = ""
    pinvi_sentry_environment: str = "development"
    pinvi_sentry_release: str = ""
    pinvi_sentry_traces_sample_rate: float = 0.1
    pinvi_sentry_profiles_sample_rate: float = 0.0

    # Prometheus metrics (Sprint 5 observability)
    pinvi_prometheus_metrics_enabled: bool = True
    pinvi_prometheus_metrics_path: str = "/metrics"
    pinvi_prometheus_exclude_paths: list[str] = Field(
        default_factory=lambda: ["/health", "/health/db", "/metrics"]
    )

    # Admin system view (T-222) — Docker Engine read API collector. The socket is not
    # mounted by default in compose; missing/denied access is reported as unknown/down.
    pinvi_docker_socket_path: str = "/var/run/docker.sock"
    pinvi_docker_status_timeout_seconds: float = 2.0
    pinvi_docker_status_container_limit: int = 80

    # Backup / Restore (ADR-022)
    pinvi_backup_dir: str = ".tmp/backups"
    pinvi_backup_script_path: str = "scripts/backup-db.sh"
    pinvi_restore_script_path: str = "scripts/restore-db.sh"
    pinvi_restore_hotswap_script_path: str = "scripts/restore-hotswap.sh"
    pinvi_backup_timeout_seconds: int = 900
    pinvi_restore_timeout_seconds: int = 3600
    pinvi_backup_schema: str = "app"
    pinvi_backup_min_free_bytes: int = 1_073_741_824
    pinvi_restore_database_url: str = ""
    pinvi_restore_hotswap_execute: bool = False
    pinvi_restore_drain_command: str = ""
    pinvi_restore_allow_no_drain: bool = False
    pinvi_restore_app_role: str = ""

    # Feature flag
    pinvi_enable_seed: bool = False

    @model_validator(mode="after")
    def validate_kor_travel_map_ops(self) -> Self:
        """canonical ops URL과 read/cancel 자격을 fail-closed로 검증한다."""

        is_production = self.pinvi_environment == "production"
        if is_production:
            try:
                admin_base_url = urlsplit(self.pinvi_kor_travel_map_admin_base_url)
                hostname = admin_base_url.hostname
                port = admin_base_url.port
            except ValueError as exc:
                raise ValueError(
                    "production PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL must be an allowed "
                    "root HTTP(S) URL on port 12701"
                ) from exc
            if (
                admin_base_url.scheme not in {"http", "https"}
                or hostname not in {"127.0.0.1", "host.docker.internal"}
                or port != 12701
                or admin_base_url.path not in {"", "/"}
                or admin_base_url.username is not None
                or admin_base_url.password is not None
                or bool(admin_base_url.query)
                or bool(admin_base_url.fragment)
            ):
                raise ValueError(
                    "production PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL must be an allowed "
                    "root HTTP(S) URL on port 12701"
                )

        read_token = (
            self.pinvi_kor_travel_map_ops_read_token.get_secret_value()
            if self.pinvi_kor_travel_map_ops_read_token is not None
            else ""
        )
        cancel_token = (
            self.pinvi_kor_travel_map_ops_cancel_token.get_secret_value()
            if self.pinvi_kor_travel_map_ops_cancel_token is not None
            else ""
        )
        if not read_token and not cancel_token and not is_production:
            return self
        if not read_token or not cancel_token:
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN and "
                "PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN must be configured together"
            )
        for env_name, token in (
            ("PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN", read_token),
            ("PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN", cancel_token),
        ):
            if len(token) < 32:
                raise ValueError(f"{env_name} must contain at least 32 characters")
            if any(character.isspace() for character in token):
                raise ValueError(f"{env_name} must not contain whitespace")
        if read_token == cancel_token:
            raise ValueError("kor-travel-map ops read/cancel tokens must differ")
        return self

    @model_validator(mode="after")
    def validate_cache_target_sync(self) -> Self:
        """paired worker credential과 exact contract pin을 fallback 없이 검증한다."""

        role_fields = (
            (
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_COMMAND_TOKEN",
                self.pinvi_kor_travel_map_cache_target_command_token,
            ),
            (
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_CONSUMER_TOKEN",
                self.pinvi_kor_travel_map_cache_target_consumer_token,
            ),
            (
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_RESTORE_FENCE_TOKEN",
                self.pinvi_kor_travel_map_cache_target_restore_fence_token,
            ),
            (
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_RECOVERY_TOKEN",
                self.pinvi_kor_travel_map_cache_target_recovery_token,
            ),
        )
        role_tokens: list[tuple[str, str]] = []
        for env_name, secret in role_fields:
            if secret is None:
                continue
            token = secret.get_secret_value()
            if len(token) < 32:
                raise ValueError(f"{env_name} must contain at least 32 characters")
            if any(character.isspace() for character in token):
                raise ValueError(f"{env_name} must not contain whitespace")
            role_tokens.append((env_name, token))
        token_values = [token for _, token in role_tokens]
        if len(set(token_values)) != len(token_values):
            raise ValueError("kor-travel-map cache target role tokens must all differ")

        protected_map_credentials = {
            value
            for value in (
                self.pinvi_kor_travel_map_service_token.strip(),
                self.pinvi_kor_travel_map_admin_service_token.strip(),
                self.pinvi_kor_travel_map_admin_proxy_secret.strip(),
                self.pinvi_kor_travel_map_public_api_key.strip(),
                self.pinvi_vworld_api_key.strip(),
                self.pinvi_kor_travel_map_ops_read_token.get_secret_value()
                if self.pinvi_kor_travel_map_ops_read_token is not None
                else "",
                self.pinvi_kor_travel_map_ops_cancel_token.get_secret_value()
                if self.pinvi_kor_travel_map_ops_cancel_token is not None
                else "",
                self.pinvi_kor_travel_map_curation_snapshot_token.get_secret_value()
                if self.pinvi_kor_travel_map_curation_snapshot_token is not None
                else "",
                self.pinvi_kor_travel_map_curation_cutover_mapping_token.get_secret_value()
                if self.pinvi_kor_travel_map_curation_cutover_mapping_token is not None
                else "",
            )
            if value
        }
        if any(token in protected_map_credentials for _, token in role_tokens):
            raise ValueError(
                "cache target role tokens must not reuse another Map trust-boundary credential"
            )

        if any(
            character.isspace() for character in self.pinvi_kor_travel_map_cache_target_consumer_id
        ):
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_CONSUMER_ID must not contain whitespace"
            )
        if not self.pinvi_kor_travel_map_cache_target_sync_enabled:
            return self
        if self.pinvi_environment == "production":
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_SYNC_ENABLED is forbidden in production "
                "until the root-owned final C7 enable boundary is implemented"
            )
        if self.pinvi_kor_travel_map_cache_target_command_token is None:
            raise ValueError("PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_COMMAND_TOKEN is required")
        if self.pinvi_kor_travel_map_cache_target_consumer_token is None:
            raise ValueError("PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_CONSUMER_TOKEN is required")
        openapi_sha = self.pinvi_kor_travel_map_cache_target_expected_openapi_sha256
        if len(openapi_sha) != 64 or openapi_sha != openapi_sha.lower():
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_EXPECTED_OPENAPI_SHA256 must be lowercase SHA-256 hex"
            )
        try:
            bytes.fromhex(openapi_sha)
        except ValueError as exc:
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_EXPECTED_OPENAPI_SHA256 must be lowercase SHA-256 hex"
            ) from exc
        if openapi_sha != KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256:
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_EXPECTED_OPENAPI_SHA256 must match the vendored service contract"
            )
        source_revision = self.pinvi_kor_travel_map_cache_target_expected_source_revision
        if (
            len(source_revision) != 40
            or source_revision != source_revision.lower()
            or any(character not in "0123456789abcdef" for character in source_revision)
        ):
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_EXPECTED_SOURCE_REVISION must be a full lowercase git SHA"
            )
        if source_revision != KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION:
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_EXPECTED_SOURCE_REVISION must match the service contract Map release revision"
            )
        if (
            self.pinvi_kor_travel_map_cache_target_expected_contract_generation
            != KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION
        ):
            raise ValueError(
                "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_EXPECTED_CONTRACT_GENERATION must match the vendored service contract"
            )
        return self

    @model_validator(mode="after")
    def validate_curation_service_principals(self) -> Self:
        """두 curation scope를 다른 Map trust boundary와 서로 분리한다."""

        curation_tokens = (
            (
                "PINVI_KOR_TRAVEL_MAP_CURATION_SNAPSHOT_TOKEN",
                self.pinvi_kor_travel_map_curation_snapshot_token,
            ),
            (
                "PINVI_KOR_TRAVEL_MAP_CURATION_CUTOVER_MAPPING_TOKEN",
                self.pinvi_kor_travel_map_curation_cutover_mapping_token,
            ),
        )
        values = [secret.get_secret_value() for _, secret in curation_tokens if secret is not None]
        if len(values) != len(set(values)):
            raise ValueError("curation snapshot and cutover mapping tokens must differ")
        protected = {
            value
            for value in (
                self.pinvi_kor_travel_map_service_token.strip(),
                self.pinvi_kor_travel_map_admin_service_token.strip(),
                self.pinvi_kor_travel_map_admin_proxy_secret.strip(),
                self.pinvi_kor_travel_map_public_api_key.strip(),
                self.pinvi_vworld_api_key.strip(),
                self.pinvi_kor_travel_map_ops_read_token.get_secret_value()
                if self.pinvi_kor_travel_map_ops_read_token is not None
                else "",
                self.pinvi_kor_travel_map_ops_cancel_token.get_secret_value()
                if self.pinvi_kor_travel_map_ops_cancel_token is not None
                else "",
                self.pinvi_kor_travel_map_cache_target_command_token.get_secret_value()
                if self.pinvi_kor_travel_map_cache_target_command_token is not None
                else "",
                self.pinvi_kor_travel_map_cache_target_consumer_token.get_secret_value()
                if self.pinvi_kor_travel_map_cache_target_consumer_token is not None
                else "",
                self.pinvi_kor_travel_map_cache_target_restore_fence_token.get_secret_value()
                if self.pinvi_kor_travel_map_cache_target_restore_fence_token is not None
                else "",
                self.pinvi_kor_travel_map_cache_target_recovery_token.get_secret_value()
                if self.pinvi_kor_travel_map_cache_target_recovery_token is not None
                else "",
            )
            if value
        }
        for env_name, secret in curation_tokens:
            if secret is None:
                continue
            token = secret.get_secret_value()
            if len(token) < 32:
                raise ValueError(f"{env_name} must contain at least 32 characters")
            if any(character.isspace() for character in token):
                raise ValueError(f"{env_name} must not contain whitespace")
            if token in protected:
                raise ValueError(f"{env_name} must not reuse another Map trust-boundary credential")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
