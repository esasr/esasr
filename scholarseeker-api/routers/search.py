from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import cfg
from services.llm_service import plan_search_query
from services.search_pipeline import SearchBudget, run_search_pipeline

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    llm_provider: str | None = None
    llm_model: str | None = None


class FullSearchRequest(SearchRequest):
    limit: int = Field(default=20, ge=1, le=50)
    max_queries: int = Field(default=4, ge=1, le=6)
    results_per_source: int = Field(default=15, ge=5, le=50)
    max_api_calls: int = Field(default=8, ge=1, le=12)


PROVIDER_LABELS = {
    "deepseek": "DeepSeek",
    "qwen": "通义千问",
    "openai": "OpenAI",
    "kimi": "Kimi",
    "custom": "自定义模型",
}


def _validate_llm(provider: str | None, model: str | None) -> tuple[str, str]:
    selected = provider or cfg.llm.active_provider
    if selected not in cfg.llm.providers:
        raise HTTPException(status_code=422, detail="不支持所选大模型平台")
    if not cfg.llm.is_provider_configured(selected):
        raise HTTPException(status_code=422, detail="所选大模型平台尚未配置 API Key")
    selected_model = model or cfg.llm.get_provider(selected).get("model", "")
    if selected_model not in cfg.llm.provider_models(selected):
        raise HTTPException(status_code=422, detail="所选模型未在该平台中配置")
    return selected, selected_model


@router.get("/providers")
async def list_llm_providers():
    providers = [
        {
            "id": name,
            "label": PROVIDER_LABELS.get(name, name),
            "models": cfg.llm.provider_models(name),
            "defaultModel": cfg.llm.get_provider(name).get("model", ""),
        }
        for name in cfg.llm.configured_providers()
    ]
    active = cfg.llm.active_provider
    default_provider = active if active in {item["id"] for item in providers} else (
        providers[0]["id"] if providers else None
    )
    default_model = (
        cfg.llm.get_provider(default_provider).get("model", "")
        if default_provider
        else None
    )
    return {
        "providers": providers,
        "default": {
            "provider": default_provider,
            "model": default_model,
        } if default_provider else None,
    }


@router.post("/analyze")
async def analyze_query(request: SearchRequest):
    provider, model = _validate_llm(request.llm_provider, request.llm_model)
    return await plan_search_query(request.query, provider, model)


@router.post("/run")
async def run_search(request: FullSearchRequest):
    provider, model = _validate_llm(request.llm_provider, request.llm_model)
    budget = SearchBudget(
        max_queries=request.max_queries,
        results_per_source=request.results_per_source,
        max_api_calls=request.max_api_calls,
    )
    return await run_search_pipeline(
        query=request.query,
        limit=request.limit,
        budget=budget,
        llm_provider=provider,
        llm_model=model,
    )
