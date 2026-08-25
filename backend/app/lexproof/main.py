"""FastAPI application for the LexProof foundation."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import blockchain_router, public_verify_router, time_machine_router, compliance_router, remediation_router, contracts_router
from .api.auth import get_current_user
from .config import get_settings
from .domains.passport.api import contract_router, router as passport_router
from .services.health import router as health_router


def create_app() -> FastAPI:
    """Create the LexProof API application."""
    app = FastAPI(title="LexProof API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    private_dependencies = [Depends(get_current_user)]
    app.include_router(passport_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(contract_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(contracts_router, prefix="/api")
    app.include_router(blockchain_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(time_machine_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(public_verify_router)
    app.include_router(compliance_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(remediation_router, prefix="/api", dependencies=private_dependencies)
    return app


app = create_app()
