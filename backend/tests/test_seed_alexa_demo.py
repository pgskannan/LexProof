from datetime import date, timedelta

from app.lexproof.domains.passport.integrity import verify_passport_integrity
from scripts.seed_alexa_demo import CONTRACT_SPECS, build_seed_plan


def test_alexa_seed_plan_has_expected_demo_data_and_anchor_eligible_acme():
    today = date(2026, 10, 12)
    plan = build_seed_plan("owner-uid", "judge-uid", owner_email="owner@example.test", today=today)

    assert [contract["name"] for contract in plan["contracts"]] == [spec["name"] for spec in CONTRACT_SPECS]
    assert len(plan["contracts"]) == 5
    assert len(plan["workflows"]) == 2
    assert plan["workflows"][0]["instance"]["status"] == "in_progress"
    assert [record["status"] for record in plan["obligations"]] == [
        "PENDING_APPROVAL",
        "EXTRACTED",
        "PENDING_APPROVAL",
    ]
    assert plan["obligations"][0]["due_date"] == (today - timedelta(days=2)).isoformat()
    assert plan["obligations"][1]["due_date"] == (today + timedelta(days=10)).isoformat()
    assert plan["obligations"][2]["due_date"] == (today + timedelta(days=25)).isoformat()
    assert plan["passport_anchor_eligible"] is True
    assert verify_passport_integrity(plan["passports"][0], [])["verified"] is True

    assert plan["workflows"][0]["instance"]["created_by"] == "judge-uid"
    assert plan["owner_uid"] != plan["judge_uid"]
    assert all(item["needs_review_reason"] is None for item in plan["obligations"])
