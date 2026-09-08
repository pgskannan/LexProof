"""FastAPI application for the LexProof foundation."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import blockchain_router, public_verify_router, time_machine_router, compliance_router, remediation_router, contracts_router, evidence_anchor_router, findings_router
from .api.search import router as search_router
from .api.notifications import router as notifications_router
from .api.audit_log import router as audit_log_router
from .api.redline_proposals import proposal_router, router as redline_proposals_router
from .api.auth import get_current_user
from .config import get_settings
from .domains.passport.api import contract_router, router as passport_router
from .services.health import router as health_router
from .api.organizations import router as organizations_router
from .api.workflows import router as workflows_router
from .api.ask import router as ask_router
from .api.counterparty import external_router as counterparty_external_router
from .api.counterparty import internal_router as counterparty_internal_router


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
    app.include_router(evidence_anchor_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(time_machine_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(public_verify_router, prefix="/api")
    app.include_router(compliance_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(remediation_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(findings_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(audit_log_router, prefix="/api")
    app.include_router(redline_proposals_router, prefix="/api")
    app.include_router(proposal_router, prefix="/api")
    app.include_router(organizations_router, prefix="/api")
    app.include_router(workflows_router, prefix="/api")
    app.include_router(ask_router, prefix="/api")
    app.include_router(counterparty_internal_router, prefix="/api")
    app.include_router(counterparty_external_router, prefix="/api")
    return app


app = create_app()
