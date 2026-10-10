"""Health checks for LexProof cloud foundations."""
from fastapi import APIRouter
from ..config import get_settings
from .firebase import firebase_is_initialized

router = APIRouter(tags=["health"])


def _status(ready: bool, service: str) -> dict[str, str]:
    return {"status": "ok" if ready else "not_configured", "service": service}


@router.get("/health")
async def health() -> dict[str, object]:
    from .paypal.startup import paypal_health

    settings = get_settings()
    is_nebius = settings.llm_provider == "nebius"
    return {
        "status": "ok",
        "service": "lexproof",
        "paypal": paypal_health(settings),
        "ai": {
            "provider": settings.llm_provider,
            "analysis_model": settings.nebius_model_analysis if is_nebius else settings.gemini_model,
            "fast_model": settings.nebius_model_fast if is_nebius else settings.gemini_model,
            "fallback_to_vertex": settings.llm_fallback_to_vertex,
            "nebius_configured": settings.has_nebius_configuration(),
        },
    }


@router.get("/health/firebase")
async def firebase_health() -> dict[str, str]:
    return _status(firebase_is_initialized() or get_settings().has_firebase_credentials(), "firebase")


@router.get("/health/gcp")
async def gcp_health() -> dict[str, str]:
    return _status(get_settings().has_gcp_project(), "google_cloud")


@router.get("/health/ai")
async def ai_health() -> dict[str, str]:
    return _status(get_settings().has_ai_configuration(), "vertex_ai")


@router.get("/health/config")
async def configuration_health() -> dict[str, object]:
    settings = get_settings()
    network = "ethereum-sepolia" if settings.ethereum_chain_id == 11155111 else f"chain-{settings.ethereum_chain_id}"
    return {
        "network": network,
        "chain_id": settings.ethereum_chain_id,
        "contract_address": settings.contract_address,
        "gemini_model": settings.gemini_model,
        "ethereum_configured": bool(settings.ethereum_rpc_url and settings.contract_address),
    }
