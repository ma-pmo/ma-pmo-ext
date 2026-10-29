"""Bilingual output — English by default, Korean via the language context or the API."""
from fastapi.testclient import TestClient

from ma_pmo.agents.gates import evaluate_gate, normalize_gate
from ma_pmo.connectors.vectordb import LocalLexicalStore
from ma_pmo.core.i18n import from_accept_language, normalize, tr, use_lang
from ma_pmo.core.scenarios import list_scenarios, run_scenario


def test_normalize_and_accept_language():
    assert normalize("ko-KR") == "ko"
    assert normalize("EN_us") == "en"
    assert normalize("fr") is None
    assert from_accept_language("fr-FR,ko;q=0.8,en;q=0.5") == "ko"


def test_tr_follows_context():
    assert tr("hello", "안녕") == "hello"
    with use_lang("ko"):
        assert tr("hello", "안녕") == "안녕"
    assert tr("hello", "안녕") == "hello"


def test_legacy_korean_gate_ids_still_work():
    assert normalize_gate("G2-계획완료") == "G2-planning"
    assert normalize_gate("G3") == "G3-execution"
    project = {"tasks": [{"task_id": "T1", "wbs": "1", "effort": 8, "deps": []}],
               "planned_start": "2026-01-05", "deadline": "2026-03-31"}
    assert evaluate_gate(project, "G1-착수")[0] == "pass"


def test_scenarios_in_both_languages():
    en = {s["id"]: s for s in list_scenarios()}
    with use_lang("ko"):
        ko = {s["id"]: s for s in list_scenarios()}
    assert en["quarterly_review"]["title"] == "Quarterly portfolio review"
    assert ko["quarterly_review"]["title"] == "분기 포트폴리오 통합 리뷰"
    assert en["quarterly_review"]["category_id"] == ko["quarterly_review"]["category_id"]

    with use_lang("ko"):
        trace = run_scenario("baseline_planning")
    assert trace["phases"][0]["title"].startswith("계획")


def test_knowledge_search_is_bilingual():
    store = LocalLexicalStore()
    en_hits = store.similarity_search("data migration delay", k=1)
    with use_lang("ko"):
        ko_hits = store.similarity_search("데이터 마이그레이션 지연", k=1)
    assert en_hits[0]["source_id"] == ko_hits[0]["source_id"] == "LL-2024-01"
    assert "migration" in en_hits[0]["title"].lower()
    assert "마이그레이션" in ko_hits[0]["title"]


def test_api_language_selection():
    from ma_pmo.api.main import app

    client = TestClient(app)
    en = client.get("/scenarios").json()
    ko_query = client.get("/scenarios?lang=ko").json()
    ko_header = client.get("/scenarios", headers={"Accept-Language": "ko-KR"}).json()
    assert en[0]["title"] != ko_query[0]["title"]
    assert ko_query[0]["title"] == ko_header[0]["title"]
