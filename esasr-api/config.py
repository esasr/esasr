"""
config.py — ESASR 配置加载器

加载策略：
  1. 读取根目录 config.yaml
  2. 此文件现在包含所有 URL、模型名等配置以及密码 / API Keys 等敏感配置
  3. 提供统一的 cfg 单例供各模块 import 使用
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# ── 读取根目录 config.yaml ────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
_CONFIG_PATH = Path(
    os.getenv("SCHOLARSEEKER_CONFIG_PATH", str(_PROJECT_ROOT / "config.yaml"))
)

with open(_CONFIG_PATH, encoding="utf-8") as _f:
    _raw: dict = yaml.safe_load(_f)


def _set_nested(path: tuple[str, ...], value: Any) -> None:
    cursor = _raw
    for key in path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[path[-1]] = value


def _env(name: str, path: tuple[str, ...], cast=str) -> None:
    value = os.getenv(name)
    if value is None or value == "":
        return
    if cast is bool:
        parsed: Any = value.casefold() in {"1", "true", "yes", "on"}
    else:
        parsed = cast(value)
    _set_nested(path, parsed)


# Container deployments and CI can override every connection or secret without
# baking the local config.yaml into an image.
for _name, _path, _cast in (
    ("SCHOLARSEEKER_DEBUG", ("app", "debug"), bool),
    ("POSTGRES_HOST", ("database", "host"), str),
    ("POSTGRES_PORT", ("database", "port"), int),
    ("POSTGRES_DB", ("database", "name"), str),
    ("POSTGRES_USER", ("database", "user"), str),
    ("POSTGRES_PASSWORD", ("database", "password"), str),
    ("REDIS_HOST", ("redis", "host"), str),
    ("REDIS_PORT", ("redis", "port"), int),
    ("REDIS_PASSWORD", ("redis", "password"), str),
    ("NEO4J_HOST", ("neo4j", "host"), str),
    ("NEO4J_BOLT_PORT", ("neo4j", "bolt_port"), int),
    ("NEO4J_USER", ("neo4j", "user"), str),
    ("NEO4J_PASSWORD", ("neo4j", "password"), str),
    ("NEO4J_DATABASE", ("neo4j", "database"), str),
    ("JWT_SECRET", ("auth", "jwt_secret"), str),
    ("LLM_ACTIVE_PROVIDER", ("llm", "active_provider"), str),
    ("DEEPSEEK_API_KEY", ("llm", "providers", "deepseek", "api_key"), str),
    ("QWEN_API_KEY", ("llm", "providers", "qwen", "api_key"), str),
    ("OPENAI_API_KEY", ("llm", "providers", "openai", "api_key"), str),
    ("KIMI_API_KEY", ("llm", "providers", "kimi", "api_key"), str),
    ("CUSTOM_LLM_API_KEY", ("llm", "providers", "custom", "api_key"), str),
    ("CUSTOM_LLM_BASE_URL", ("llm", "providers", "custom", "base_url"), str),
    ("CUSTOM_LLM_MODEL", ("llm", "providers", "custom", "model"), str),
    ("SEMANTIC_SCHOLAR_API_KEY", ("academic_apis", "semantic_scholar", "api_key"), str),
    ("OPENALEX_API_KEY", ("academic_apis", "openalex", "api_key"), str),
    ("OPENALEX_EMAIL", ("academic_apis", "openalex", "email"), str),
    ("CROSS_ENCODER_ENABLED", ("ranking", "cross_encoder", "enabled"), bool),
    ("CROSS_ENCODER_MODEL", ("ranking", "cross_encoder", "model"), str),
    ("CROSS_ENCODER_DEVICE", ("ranking", "cross_encoder", "device"), str),
):
    _env(_name, _path, _cast)


class _Namespace:
    """将嵌套 dict 递归转换为可用属性访问的对象。"""

    def __init__(self, data: dict):
        for k, v in data.items():
            setattr(self, k, _Namespace(v) if isinstance(v, dict) else v)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __repr__(self) -> str:
        return f"_Namespace({self.__dict__})"


class _Config:
    """顶层配置对象，提供各子系统的配置访问入口。"""

    def __init__(self, raw: dict):
        self._raw = raw
        self.app = _Namespace(raw.get("app", {}))
        self.auth = _Namespace(raw.get("auth", {}))
        self._db_raw = raw.get("database", {})
        self._neo4j_raw = raw.get("neo4j", {})
        self._redis_raw = raw.get("redis", {})
        self._llm_raw = raw.get("llm", {})
        self._academic_raw = raw.get("academic_apis", {})
        self._ranking_raw = raw.get("ranking", {})

    # ── PostgreSQL ─────────────────────────────────────────────────────────────

    @property
    def db(self) -> _Namespace:
        return _Namespace(self._db_raw)

    @property
    def postgres_url(self) -> str:
        d = self._db_raw
        return (
            f"postgresql+asyncpg://{d.get('user', '')}:{d.get('password', '')}"
            f"@{d.get('host', 'localhost')}:{d.get('port', 5432)}/{d.get('name', '')}"
        )

    @property
    def postgres_url_sync(self) -> str:
        d = self._db_raw
        return (
            f"postgresql+psycopg2://{d.get('user', '')}:{d.get('password', '')}"
            f"@{d.get('host', 'localhost')}:{d.get('port', 5432)}/{d.get('name', '')}"
        )

    # ── Neo4j ─────────────────────────────────────────────────────────────────

    @property
    def neo4j(self) -> _Namespace:
        return _Namespace(self._neo4j_raw)

    @property
    def neo4j_bolt_url(self) -> str:
        d = self._neo4j_raw
        return f"bolt://{d.get('host', 'localhost')}:{d.get('bolt_port', 7687)}"

    @property
    def neo4j_password(self) -> str:
        return self._neo4j_raw.get("password", "")

    # ── Redis ─────────────────────────────────────────────────────────────────

    @property
    def redis(self) -> _Namespace:
        return _Namespace(self._redis_raw)

    @property
    def redis_url(self) -> str:
        d = self._redis_raw
        pwd = d.get("password", "")
        auth = f":{pwd}@" if pwd else ""
        return f"redis://{auth}{d.get('host', 'localhost')}:{d.get('port', 6379)}/{d.get('db', 0)}"

    # ── JWT ───────────────────────────────────────────────────────────────────

    @property
    def jwt_secret(self) -> str:
        return self._raw.get("auth", {}).get(
            "jwt_secret", "scholarseeker-secret-key-change-in-production-2024"
        )

    # ── LLM ───────────────────────────────────────────────────────────────────

    @property
    def llm(self) -> "_LLMConfig":
        return _LLMConfig(self._llm_raw)

    # ── 学术数据源 ─────────────────────────────────────────────────────────────

    @property
    def semantic_scholar(self) -> _Namespace:
        return _Namespace(self._academic_raw.get("semantic_scholar", {}))

    @property
    def arxiv(self) -> _Namespace:
        return _Namespace(self._academic_raw.get("arxiv", {}))

    @property
    def openalex(self) -> _Namespace:
        return _Namespace(self._academic_raw.get("openalex", {}))

    @property
    def ranking(self) -> _Namespace:
        return _Namespace(self._ranking_raw)


class _LLMConfig:
    def __init__(self, raw: dict):
        self._raw = raw
        self.active_provider: str = raw.get("active_provider", "custom")
        self.providers: dict = raw.get("providers", {})

    def _active(self) -> dict:
        return self.providers.get(self.active_provider, {})

    @property
    def base_url(self) -> str:
        return self._active().get("base_url", "")

    @property
    def model(self) -> str:
        return self._active().get("model", "gpt-3.5-turbo")

    @property
    def timeout(self) -> int:
        return int(self._active().get("timeout", 30))

    @property
    def api_key(self) -> str:
        return self._active().get("api_key", "")

    def get_provider(self, name: str) -> _Namespace:
        return _Namespace(self.providers.get(name, {}))

    def provider_models(self, name: str) -> list[str]:
        provider = self.providers.get(name, {})
        configured = provider.get("models")
        if isinstance(configured, list):
            models = [str(model).strip() for model in configured if str(model).strip()]
            if models:
                return models
        default_model = str(provider.get("model", "")).strip()
        return [default_model] if default_model else []

    def is_provider_configured(self, name: str) -> bool:
        provider = self.providers.get(name, {})
        api_key = str(provider.get("api_key", "")).strip()
        normalized = api_key.casefold()
        return bool(
            api_key
            and not normalized.startswith(("your_", "your-", "replace_", "change_me"))
            and "api_key_here" not in normalized
        )

    def configured_providers(self) -> list[str]:
        return [
            name
            for name in self.providers
            if self.is_provider_configured(name)
        ]


# ── 全局单例 ──────────────────────────────────────────────────────────────────
cfg = _Config(_raw)
