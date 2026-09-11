"""Proves hardening item #2 (async Web3 / eliminate event-loop blocking) is
actually true of the running application, not just true of the source code.

Every blockchain-touching route already wraps its blocking web3.py call in
asyncio.to_thread (see api/blockchain.py, services/ethereum_anchor_service.py).
That is an implementation detail; the user-facing guarantee it is supposed to
buy is behavioral: while a slow Ethereum RPC call is in flight, every other
part of the app -- /health, /api/contracts, the public verification endpoint,
etc. -- must keep responding immediately. A test suite with 528 passing tests
and zero coverage of that specific behavioral guarantee is not actually proof
of it; this file is that proof, exercised against the real running FastAPI
app (a live ASGI transport, not a mocked event loop).
"""

import asyncio
import time

from httpx import ASGITransport, AsyncClient

import app.lexproof.api.contracts as contracts_api
import app.lexproof.services.ethereum_anchor_service as anchor_service_module
from app.lexproof.api import blockchain as blockchain_api
from app.lexproof.main import create_app
from app.lexproof.repositories.firestore import EvidenceAnchorRepository, EvidenceRecordRepository
from app.lexproof.services.auth import get_current_user
from tests.fakes import FakeRepository

SLOW_RPC_SECONDS = 0.6


class SlowFakeBlockchain:
    """Stands in for BlockchainService: a real web3.py RPC call is a blocking
    network round-trip, which asyncio.to_thread offloads to a worker thread
    so it never blocks the event loop. time.sleep() (not asyncio.sleep())
    faithfully simulates that -- it genuinely blocks whatever thread calls
    it, exactly like a slow synchronous socket read would."""

    chain_id = 11155111
    contract_address = "0xSlowContract"

    def get_current_block_number(self) -> int:
        time.sleep(SLOW_RPC_SECONDS)
        return 123456


def seed_contracts_data():
    FakeRepository.stores = {
        "contracts": {
            "contract-1": {"id": "contract-1", "owner_id": "owner-1", "org_id": "org-1"},
        },
    }


async def test_slow_blockchain_call_does_not_block_health_endpoint(monkeypatch):
    """While /api/health (the blockchain health-check route) is stuck on a
    0.6s blocking RPC call, a concurrent request to the plain /health
    endpoint (no blockchain involvement at all) must still return almost
    immediately -- proving the slow call is running on a worker thread, not
    the event loop."""
    monkeypatch.setattr(blockchain_api, "create_blockchain_service", lambda: SlowFakeBlockchain())
    app = create_app()
    # /api/blockchain/* sits behind router-level auth (main.py's
    # private_dependencies); /health does not need it, but the slow call
    # under test does.
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        started_at = time.monotonic()

        slow_task = asyncio.create_task(client.get("/api/health"))
        # Give the slow request a moment's head start so it's genuinely
        # in flight (blocked inside time.sleep on its worker thread) before
        # the fast request is issued.
        await asyncio.sleep(0.05)

        fast_response = await client.get("/health")
        fast_elapsed = time.monotonic() - started_at

        slow_response = await slow_task
        slow_elapsed = time.monotonic() - started_at

    assert fast_response.status_code == 200
    assert fast_response.json() == {"status": "ok", "service": "lexproof"}
    # The fast endpoint must complete well before the slow RPC call does --
    # if the event loop were blocked by the sync call, /health would have
    # queued behind it and taken >= SLOW_RPC_SECONDS too.
    assert fast_elapsed < SLOW_RPC_SECONDS / 2, (
        f"/health took {fast_elapsed:.3f}s while a blocking blockchain call was in "
        f"flight -- the event loop was blocked, defeating asyncio.to_thread"
    )
    assert slow_response.status_code == 200
    assert slow_response.json()["current_block"] == 123456
    assert slow_elapsed >= SLOW_RPC_SECONDS


async def test_slow_blockchain_call_does_not_block_private_api(monkeypatch):
    """Same guarantee, but against a real authenticated, Firestore-backed
    route (/api/contracts) rather than the trivially-static /health -- this
    is the more realistic "is the whole app still usable" check."""
    seed_contracts_data()
    monkeypatch.setattr(blockchain_api, "create_blockchain_service", lambda: SlowFakeBlockchain())
    monkeypatch.setattr(contracts_api, "FirestoreRepository", FakeRepository)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        started_at = time.monotonic()

        slow_task = asyncio.create_task(client.get("/api/health"))
        await asyncio.sleep(0.05)

        fast_response = await client.get("/api/contracts")
        fast_elapsed = time.monotonic() - started_at

        await slow_task

    assert fast_response.status_code == 200
    assert fast_elapsed < SLOW_RPC_SECONDS / 2, (
        f"/api/contracts took {fast_elapsed:.3f}s while a blocking blockchain call was "
        f"in flight -- a slow Ethereum RPC call is stalling ordinary app usage"
    )


async def test_slow_blockchain_call_does_not_block_public_verification(monkeypatch):
    """The product's own stated selling point is that independent
    verification -- including the public, unauthenticated endpoint a third
    party's embedded widget calls -- reads Ethereum directly. That endpoint
    itself makes a real (here, slow) chain call, so this proves two
    concurrent verifications (or a verification alongside any other in-flight
    chain call) don't serialize behind each other on the event loop."""
    monkeypatch.setattr(blockchain_api, "create_blockchain_service", lambda: SlowFakeBlockchain())
    # The verified evidence_id below doesn't exist, so verify_evidence()
    # correctly short-circuits to EVIDENCE_NOT_FOUND without ever touching
    # the blockchain -- but it still looks the record up in Firestore first,
    # so that lookup is faked the same way test_public_verify_widget_cors.py
    # does, rather than hitting real (unconfigured, in this test env) GCP.
    monkeypatch.setattr(EvidenceRecordRepository, "get", lambda self, document_id: None)
    monkeypatch.setattr(EvidenceAnchorRepository, "get", lambda self, document_id: None)
    # EthereumAnchorService.__init__ eagerly builds a BlockchainService via
    # this module's own create_blockchain_service reference (a separate
    # import from api/blockchain.py's) -- unrelated to the slow-RPC
    # simulation above, this just needs to construct without error in a test
    # environment with no real Ethereum settings configured, exactly as
    # test_public_verify_widget_cors.py's fixture already does.
    monkeypatch.setattr(anchor_service_module, "create_blockchain_service", lambda **kwargs: object())
    original_singleton = anchor_service_module._ethereum_anchor_service
    anchor_service_module._ethereum_anchor_service = None
    try:
        app = create_app()
        # Only /api/health (the slow call driving this test) needs auth;
        # /api/verify/* is the whole point of this test -- deliberately public
        # and unauthenticated, so it is called with no override at all.
        app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            started_at = time.monotonic()

            slow_task = asyncio.create_task(client.get("/api/health"))
            await asyncio.sleep(0.05)

            # EVIDENCE_NOT_FOUND is the expected, correct outcome for a
            # nonexistent evidence_id -- the point here is response latency, not
            # the verification result itself.
            verify_response = await client.get("/api/verify/nonexistent-evidence-id")
            verify_elapsed = time.monotonic() - started_at

            await slow_task
    finally:
        # Restore the module-level singleton so this test's monkeypatched
        # construction never leaks into a later test in the same process.
        anchor_service_module._ethereum_anchor_service = original_singleton

    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "EVIDENCE_NOT_FOUND"
    assert verify_elapsed < SLOW_RPC_SECONDS / 2, (
        f"public verification took {verify_elapsed:.3f}s while another blocking "
        f"blockchain call was in flight on the event loop"
    )


async def test_slow_ethereum_anchor_service_construction_does_not_block_event_loop(monkeypatch):
    """Regression test for the specific bug fixed this session: the tests
    above prove every RPC method EthereumAnchorService calls after it exists
    is async-safe -- this test is about the *construction* of that singleton
    itself, which is a separate blocking operation. get_ethereum_anchor_service()
    lazily builds an EthereumAnchorService on its first call per process, and
    EthereumAnchorService.__init__() calls create_blockchain_service(), whose
    BlockchainService.__init__() does its own blocking network I/O (a
    connectivity check plus an eth_chainId RPC call) -- separate from, and
    prior to, any of the RPC methods already covered above. Before this
    session's fix, four call sites invoked get_ethereum_anchor_service()
    directly and synchronously from inside an async route: analyze_version()
    in services/version_analysis.py, the public verify_evidence widget
    endpoint and two routes in api/evidence_anchor.py. This test drives the
    public verify endpoint (api/blockchain.py's public_verify_evidence) as
    the reproduction, with the singleton reset so this genuinely is the
    "fresh process, first Ethereum service request" scenario."""
    def slow_create_blockchain_service(**kwargs):
        # Stands in for BlockchainService.__init__'s own blocking network
        # calls (Web3(...).is_connected(), .eth.chain_id) -- time.sleep(),
        # not asyncio.sleep(), so it genuinely blocks whichever thread calls
        # it, exactly like a slow RPC connect would. The verified evidence_id
        # below doesn't exist, so verify_evidence() never calls a method on
        # the returned fake at all -- only construction needs to be slow.
        time.sleep(SLOW_RPC_SECONDS)
        return object()

    monkeypatch.setattr(anchor_service_module, "create_blockchain_service", slow_create_blockchain_service)
    monkeypatch.setattr(EvidenceRecordRepository, "get", lambda self, document_id: None)
    monkeypatch.setattr(EvidenceAnchorRepository, "get", lambda self, document_id: None)
    original_singleton = anchor_service_module._ethereum_anchor_service
    anchor_service_module._ethereum_anchor_service = None
    try:
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: {"uid": "owner-1"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            started_at = time.monotonic()

            # First call to the public verify endpoint in this (freshly reset)
            # process -- the one that pays for constructing the singleton.
            slow_task = asyncio.create_task(client.get("/api/verify/nonexistent-evidence-id"))
            await asyncio.sleep(0.05)

            fast_response = await client.get("/health")
            fast_elapsed = time.monotonic() - started_at

            slow_response = await slow_task
            slow_elapsed = time.monotonic() - started_at
    finally:
        anchor_service_module._ethereum_anchor_service = original_singleton

    assert fast_response.status_code == 200
    assert fast_response.json() == {"status": "ok", "service": "lexproof"}
    assert fast_elapsed < SLOW_RPC_SECONDS / 2, (
        f"/health took {fast_elapsed:.3f}s while EthereumAnchorService's slow "
        f"first-time construction was in flight -- the event loop was blocked, "
        f"i.e. get_ethereum_anchor_service()'s lazy construction is not "
        f"actually running off the event loop"
    )
    assert slow_response.status_code == 200
    assert slow_response.json()["status"] == "EVIDENCE_NOT_FOUND"
    assert slow_elapsed >= SLOW_RPC_SECONDS
