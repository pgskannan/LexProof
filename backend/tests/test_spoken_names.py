from app.lexproof.mcp_server.spoken_names import (
    anchored_passport_phrase,
    count_phrase,
    spoken_contract_name,
)


def test_spoken_contract_name_removes_upload_prefix_and_preserves_acronyms():
    assert spoken_contract_name("CONTRACT_02_MSA_MediumRisk.docx") == "MSA Medium Risk"
    assert spoken_contract_name("CONTRACT_03_SaaS_HighRisk.docx") == "SaaS High Risk"


def test_anchored_passport_counts_have_correct_singular_and_plural_grammar():
    assert anchored_passport_phrase(1) == "1 has an anchored proof passport"
    assert anchored_passport_phrase(2) == "2 have anchored proof passports"


def test_count_phrases_pluralize_payment_and_item():
    assert count_phrase(1, "payment") == "1 payment"
    assert count_phrase(1, "item") == "1 item"
    assert count_phrase(2, "item") == "2 items"