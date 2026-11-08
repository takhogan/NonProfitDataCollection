"""Campaign field suggestions (fallback path), persistence, and typed results."""
from dash import campaign_fields as CF
from dash import schemas as S


# ---- Pure suggestion logic (no network) ------------------------------------

def test_fallback_without_api_key_is_valid():
    req = S.SuggestFieldsRequest(name="Outage Watch", purpose="track outages",
                                 collection_template_id="power_water_outages")
    r = CF.suggest_fields(req, {"mission": "relief"}, api_key="", model="gpt-4o-mini")
    assert r.source == "fallback"
    assert r.model is None
    assert 5 <= len(r.fields) <= 8
    # Always includes area, first.
    assert r.fields[0].id == "area" and r.fields[0].kind == "core"
    # 3–5 recommended.
    assert 3 <= sum(f.recommended for f in r.fields) <= 5
    # Core fields keep core_key; custom kinds never carry one.
    for f in r.fields:
        if f.kind == "core":
            assert f.core_key is not None
        else:
            assert f.core_key is None


def test_unknown_template_falls_back_generically():
    req = S.SuggestFieldsRequest(name="X", collection_template_id="does_not_exist")
    r = CF.suggest_fields(req, None, api_key="", model="m")
    assert r.source == "fallback"
    assert any(f.id == "area" for f in r.fields)
    assert 5 <= len(r.fields) <= 8


def _field(fid, kind, **kw):
    return S.CampaignField(id=fid, label_es="", label_en=fid, question_es="",
                           question_en="", kind=kind, **kw)


def test_typed_aggregates():
    fields = [
        _field("kids", "boolean"),
        _field("days", "number", unit="days"),
        _field("hrs", "duration", unit="hours"),
        _field("shelter", "choice", options=[
            S.CampaignFieldOption(value="safe", label_es="", label_en=""),
            S.CampaignFieldOption(value="damaged", label_es="", label_en=""),
        ]),
        _field("note", "text"),
        _field("area", "core", core_key="area"),  # core is skipped
    ]
    answers = [
        {"kids": True, "days": "3", "hrs": 4, "shelter": "safe", "note": "hi"},
        {"kids": False, "days": 5, "hrs": 10, "shelter": "damaged", "note": ""},
        {"kids": "yes", "hrs": 6, "shelter": "safe"},
    ]
    res = CF.aggregate_results("camp-1", fields, answers)
    assert res.total_reports == 3
    by = {a.field_id: a for a in res.aggregates}
    assert "area" not in by  # core skipped
    assert by["kids"].yes_pct == 66.7 and by["kids"].responses == 3
    assert by["days"].avg == 4.0 and by["days"].min == 3.0 and by["days"].max == 5.0
    assert by["days"].responses == 2
    assert by["hrs"].median == 6.0
    assert by["shelter"].counts == {"safe": 2, "damaged": 1}
    assert by["note"].responses == 1  # one non-empty


def test_empty_aggregates_when_no_data():
    fields = [_field("kids", "boolean"),
              _field("shelter", "choice", options=[
                  S.CampaignFieldOption(value="safe", label_es="", label_en="")])]
    res = CF.aggregate_results("camp-1", fields, [])
    assert res.total_reports == 0
    assert len(res.aggregates) == 2
    assert res.aggregates[0].responses == 0 and res.aggregates[0].yes_pct is None
    # choice seeds every option at 0
    assert res.aggregates[1].counts == {"safe": 0}


# ---- Live endpoints --------------------------------------------------------

def test_suggest_fields_endpoint(client, auth):
    r = client.post("/campaigns/suggest-fields", headers=auth,
                    json={"name": "Nov Watch", "purpose": "outages",
                          "collection_template_id": "power_water_outages"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] in ("llm", "fallback")
    assert 5 <= len(body["fields"]) <= 8
    assert any(f["id"] == "area" for f in body["fields"])


def test_create_persists_fields_and_results(client, auth):
    fields = [
        {"id": "area", "label_es": "", "label_en": "Area", "question_es": "",
         "question_en": "", "kind": "core", "core_key": "area", "recommended": True},
        {"id": "kids", "label_es": "", "label_en": "Kids", "question_es": "",
         "question_en": "", "kind": "boolean", "recommended": True},
    ]
    created = client.post("/campaigns", headers=auth, json={
        "name": "Field Test", "collection_template_id": "food_security",
        "areas": ["Hialeah"], "fields": fields}).json()
    assert [f["id"] for f in created["fields"]] == ["area", "kids"]

    # GET returns the stored fields.
    listed = client.get("/campaigns", headers=auth).json()
    mine = next(c for c in listed if c["id"] == created["id"])
    assert [f["id"] for f in mine["fields"]] == ["area", "kids"]

    # Results: empty aggregates are fine (no data for this new campaign).
    res = client.get(f"/campaigns/{created['id']}/results", headers=auth).json()
    assert res["campaign_id"] == created["id"]
    # 'area' is core -> skipped; 'kids' is a custom boolean aggregate.
    ids = {a["field_id"] for a in res["aggregates"]}
    assert ids == {"kids"}


def test_results_404_for_unknown_campaign(client, auth):
    r = client.get("/campaigns/nope/results", headers=auth)
    assert r.status_code == 404
