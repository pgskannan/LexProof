"""FastAPI application for the LexProof foundation."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

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

    @app.middleware("http")
    async def security_headers(request, call_next):
        """Data-security hardening: standard defensive response headers on every

        response. None of these require external configuration -- they are a
        complete, always-on protection, not a stub.
        """
        # The public-verification widget's CORS preflight has to be answered
        # here, before the app-wide CORSMiddleware below gets a chance to see
        # it: Starlette's CORSMiddleware intercepts every OPTIONS preflight
        # for the whole app (it has no concept of "this path uses a
        # different, more open policy") and rejects any origin outside the
        # restricted allowlist with a 400 -- which would reject a legitimate
        # third-party site before the request ever reaches the wildcard-CORS
        # sub-app mounted at /api/verify. Actual (non-preflight) requests to
        # /api/verify/* don't hit this: the restricted CORSMiddleware simply
        # passes them through unchanged (it only adds/withholds its own
        # header, it doesn't block), and the mounted sub-app's own
        # CORSMiddleware adds the wildcard Access-Control-Allow-Origin to the
        # real response further down the stack.
        if (
            request.method == "OPTIONS"
            and request.url.path.startswith("/api/verify/")
            and "access-control-request-method" in request.headers
        ):
            preflight = PlainTextResponse("OK", status_code=200)
            preflight.headers["Access-Control-Allow-Origin"] = "*"
            preflight.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            preflight.headers["Access-Control-Allow-Headers"] = request.headers.get(
                "access-control-request-headers", "*"
            )
            return preflight

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    app.include_router(health_router)
    private_dependencies = [Depends(get_current_user)]
    app.include_router(passport_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(contract_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(contracts_router, prefix="/api")
    app.include_router(blockchain_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(evidence_anchor_router, prefix="/api", dependencies=private_dependencies)
    app.include_router(time_machine_router, prefix="/api", dependencies=private_dependencies)

    # Embeddable public-verification widget (Task #108): a third-party site
    # embeds this and calls GET /api/verify/{evidence_id} directly with
    # fetch() from whatever origin it's on, so that one endpoint needs a
    # fully open CORS policy -- while every other endpoint in this app must
    # keep the restricted origin allowlist set on the main app above.
    # CORSMiddleware is one policy per ASGI app, so the scoping is done with
    # a small, single-route sub-application carrying its own wildcard CORS
    # policy, mounted only at the exact "/api/verify" path -- nothing else
    # in the app is reachable through this mount, and the main app's
    # restricted CORS policy is completely unaffected.
    verify_app = FastAPI(title="LexProof Public Verification Widget")
    verify_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # required alongside a wildcard origin -- browsers reject "*" + credentials
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )
    verify_app.include_router(public_verify_router)
    app.mount("/api/verify", verify_app)

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
