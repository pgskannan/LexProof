"""Unit tests for the passport router's engine/repository configuration
mechanism (domains/passport/api/router.py).

This module used to hold a process-wide singleton `PassportService` (armed
via configure_passport_service()) that get_passport_service() would fall
back to reading with a hardcoded tenant_id="read-only" identity when unarmed
-- a landmine that caused two separate real tenant-scoping bugs earlier in
this project. The fix replaced that singleton with two plain module-level
values (the analysis engine callable and the repository) plus an
"is configured" flag; no function returns a shared PassportService instance
carrying a baked-in identity any more. These tests guard both properties.
"""

import importlib


def _fresh_router():
    """Import a fresh copy of the router module with its own module-level
    state, so tests don't leak configuration into each other via the
    process-wide singleton the real app uses."""
    return importlib.import_module("app.lexproof.domains.passport.api.router")


def test_get_passport_service_singleton_getter_no_longer_exists():
    """The dangerous fallback-to-read-only singleton getter must stay gone --
    a future endpoint reaching for "the obvious function name" should not be
    able to reintroduce the cross-tenant bug class this refactor closed."""
    router = _fresh_router()
    assert not hasattr(router, "get_passport_service")
    assert not hasattr(router, "_passport_service")


def test_create_passport_service_uses_configured_engine_and_repository():
    router = _fresh_router()

    async def fake_engine(document, policy):
        return {}

    sentinel_repository = object()
    router.configure_passport_service(
        router.PassportService(analysis_engine=fake_engine, user_id="whatever", tenant_id="whatever", repository=sentinel_repository)
    )

    service = router.get_create_passport_service({"uid": "real-caller"})
    assert service.analysis_engine is fake_engine
    assert service.repository is sentinel_repository
    # Identity always comes from the real caller passed in, never from
    # whatever identity the configuring PassportService happened to carry.
    assert service.user_id == "real-caller"
    assert service.tenant_id == "real-caller"


def test_create_passport_service_falls_back_when_never_configured():
    router = _fresh_router()
    router._configured = False
    router._configured_analysis_engine = None
    router._configured_repository = None

    service = router.get_create_passport_service({"uid": "real-caller"})
    assert service.analysis_engine is router._analysis_engine
    assert service.user_id == "real-caller"
    assert service.tenant_id == "real-caller"


def test_read_passport_service_identity_always_comes_from_caller():
    router = _fresh_router()
    router.configure_passport_service(
        router.PassportService(analysis_engine=lambda *_: None, user_id="configurer", tenant_id="configurer")
    )
    service = router.get_read_passport_service({"uid": "real-caller"})
    assert service.user_id == "real-caller"
    assert service.tenant_id == "real-caller"
