"""Pure unit tests: parsing, redaction, extraction, adapter payloads, rate limit."""
from __future__ import annotations

import json

import httpx
import pytest

from app.whatsapp import adapter as A
from app.whatsapp import extraction as X
from app.whatsapp.parsing import (
    AreaCandidate, Option, command_of, is_dont_know, match_areas, match_option, parse_int,
    redact, yes_no,
)
from app.whatsapp.sender import TokenBucket


@pytest.mark.parametrize("text,cmd", [
    ("AYUDA", "help"), ("Menú", "menu"), ("menu", "menu"), ("  dónde ", "where"),
    ("BAJA", "optout"), ("atrás", "back"), ("Permisos", "permissions"), ("borrar", "delete"),
    ("necesito ayuda con el agua", None),
])
def test_commands_whole_message_accent_insensitive(text, cmd):
    assert command_of(text) == cmd


def test_yes_no_and_dont_know():
    assert yes_no("Sí") is True and yes_no("si claro") is True
    assert yes_no("No") is False and yes_no("no gracias") is False
    assert yes_no("no sé") is None and is_dont_know("No sé")
    assert yes_no("depende") is None


def test_parse_int():
    assert parse_int("5 personas") == 5
    assert parse_int("cinco") == 5
    assert parse_int("entre 3 y 5") is None  # ambiguous: re-ask
    assert parse_int("900", hi=500) is None


def test_match_option_by_id_number_and_synonym():
    opts = [Option("a", "Sí hay", synonyms=("hay",)), Option("b", "No hay")]
    assert match_option(opts, choice_id="b", text=None).id == "b"
    assert match_option(opts, choice_id=None, text="1").id == "a"
    assert match_option(opts, choice_id=None, text="no hay").id == "b"
    assert match_option(opts, choice_id=None, text="hay").id == "a"
    assert match_option(opts, choice_id=None, text="3") is None


def test_area_matching_alias_ambiguity_and_miss():
    c = [AreaCandidate("1", "Sector CAT-1", ("cat 1",)),
         AreaCandidate("2", "Sector CAT-2", ("cat 2",)),
         AreaCandidate("3", "San Juan")]
    assert [x.id for x in match_areas(c, "cat 1")] == ["1"]
    assert [x.id for x in match_areas(c, "vivo en san juan")] == ["3"]
    assert len(match_areas(c, "sector cat")) >= 2  # ambiguous: offer candidates
    assert match_areas(c, "Petare") == []


def test_redact_removes_contact_details():
    t = redact("llámame al +58 412-555-1234 o a ana@x.org, cédula V-12345678, www.x.com")
    assert "555" not in t and "ana@" not in t and "12345678" not in t and "www" not in t
    assert len(redact("a" * 1000)) == 280


def test_validate_drops_bad_types_ranges_and_enums():
    out = X.validate({"electricity_status": "broken", "drinking_people": 9999,
                      "water_status": "unavailable", "needs_charging": "yes",
                      "charging_device_count": 2, "area_text": "  Catedral ",
                      "drinking_liters": True})
    assert out == {"water_status": "unavailable", "charging_device_count": 2,
                   "area_text": "Catedral"}
    assert X.validate("nope") is None


def test_schema_is_strict_and_complete():
    assert X.SCHEMA["additionalProperties"] is False
    assert set(X.SCHEMA["required"]) == set(X.SCHEMA["properties"])
    for spec in X.SCHEMA["properties"].values():
        assert "null" in spec["type"]


def test_openai_extractor_request_and_response(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, body=json, headers=headers)
        content = '{"water_status": "unavailable", "drinking_people": 3}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(X.httpx, "post", fake_post)
    ex = X.OpenAIExtractor(api_key="sk-test", model="gpt-test")
    out = ex.extract(question="¿Llega agua?", answer="no llega, somos 3, tel 0412 555 1234")
    assert out == {"water_status": "unavailable", "drinking_people": 3}
    assert seen["url"].endswith("/chat/completions")
    rf = seen["body"]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    user = seen["body"]["messages"][1]["content"]
    assert "555" not in user and "[número]" in user


def test_openai_extractor_failures_return_none(monkeypatch):
    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(X.httpx, "post", boom)
    assert X.OpenAIExtractor("k", "m").extract(question="q", answer="a") is None

    def refusal(url, **k):
        return httpx.Response(200, json={"choices": [{"message": {"refusal": "no",
                                                                   "content": None}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(X.httpx, "post", refusal)
    assert X.OpenAIExtractor("k", "m").extract(question="q", answer="a") is None


def test_extractor_off_by_default(monkeypatch):
    X.set_extractor(None)
    monkeypatch.setattr(X, "_configured", False)
    assert X.get_extractor() is None


def test_graph_payloads():
    p = A.graph_payload("58412", {"kind": "buttons", "body": "¿?", "buttons": [
        {"id": "yes", "title": "Sí"}, {"id": "no", "title": "No"}]}, callback_data="ob-1")
    assert p["interactive"]["type"] == "button"
    assert p["biz_opaque_callback_data"] == "ob-1"
    rows = [{"id": str(i), "title": "x" * 40} for i in range(12)]
    p = A.graph_payload("58412", {"kind": "list", "body": "b", "rows": rows})
    sec = p["interactive"]["action"]["sections"][0]["rows"]
    assert len(sec) == 10 and len(sec[0]["title"]) == 24
    p = A.graph_payload("58412", {"kind": "template", "name": "report_received_v1",
                                  "language": "es", "params": ["Catedral"]})
    assert p["template"]["components"][0]["parameters"][0]["text"] == "Catedral"


def _graph(monkeypatch, exc=None, status=200, body=None):
    def fake_post(url, json=None, headers=None, timeout=None):
        if exc:
            raise exc
        return httpx.Response(status, json=body or {}, request=httpx.Request("POST", url))

    monkeypatch.setattr(A.httpx, "post", fake_post)
    return A.GraphApiAdapter(token="t", base_url="https://graph.test", api_version="v0")


def test_graph_error_classification(monkeypatch):
    msg = {"kind": "text", "body": "hola"}
    with pytest.raises(A.SendError) as e:
        _graph(monkeypatch, exc=httpx.ConnectError("x")).send(phone_number_id="1", to="2",
                                                              message=msg)
    assert e.value.retryable and not e.value.uncertain
    with pytest.raises(A.SendError) as e:
        _graph(monkeypatch, exc=httpx.ReadTimeout("x")).send(phone_number_id="1", to="2",
                                                             message=msg)
    assert e.value.uncertain and not e.value.retryable
    with pytest.raises(A.SendError) as e:
        _graph(monkeypatch, status=400, body={"error": {"code": 131047, "message": "window"}}
               ).send(phone_number_id="1", to="2", message=msg)
    assert not e.value.retryable and "131047" in str(e.value)
    with pytest.raises(A.SendError) as e:
        _graph(monkeypatch, status=429).send(phone_number_id="1", to="2", message=msg)
    assert e.value.retryable
    ok = _graph(monkeypatch, body={"messages": [{"id": "wamid.X"}]}).send(
        phone_number_id="1", to="2", message=msg)
    assert ok.provider_message_id == "wamid.X"


def test_token_bucket_waits_when_empty():
    slept = []
    b = TokenBucket(rate=2.0, burst=1)

    def fake_sleep(s):
        slept.append(s)
        b.updated -= s  # pretend time passed

    b.take(fake_sleep)
    b.take(fake_sleep)
    assert slept and slept[0] == pytest.approx(0.5, abs=0.05)


def test_catalog_respects_whatsapp_limits():
    from app.whatsapp import catalog as C

    for opts in (C.SERVICE_STATUS, C.SINCE, C.SUPPLY, C.DEVICES, C.MENU, C.SECTIONS,
                 C.YES_NO, C.YES_NO_DK):
        m = C.ask("q", opts)
        if m["kind"] == "buttons":
            assert all(len(x["title"]) <= A.BUTTON_TITLE for x in m["buttons"])
        else:
            assert all(len(r["title"]) <= A.ROW_TITLE for r in m["rows"])
            assert all(len(r.get("description") or "") <= A.ROW_DESC for r in m["rows"])
    assert json.dumps(C.notice("Metron Reporter", "Org"))
