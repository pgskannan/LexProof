import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from app.lexproof.repositories.firestore import FirestoreRepository, EvidenceAnchorRepository
from app.lexproof.config import get_settings
import asyncio

from app.lexproof.services.ethereum_anchor_service import get_ethereum_anchor_service

evidence_id = sys.argv[1]
settings = get_settings()
repo = FirestoreRepository("evidence_records", settings=settings)
anchor_repo = EvidenceAnchorRepository("evidence_anchors", settings=settings)
verifier = get_ethereum_anchor_service(settings=settings, repository=anchor_repo, evidence_repository=repo)
result = asyncio.run(verifier.verify_evidence(evidence_id))
print(result)
