import types
import pytest
import diagnostic


SAMPLE_DATA = {
    "0": {
        "DepotNumber": 6123,
        "VehicleId": 1,
        "Indicators": {
            "summary-state": {"Value": "green", "Legend": "ok"},
            "brd": {
                "Value": "red",
                "Legend": "Светодиодные табло <br>  Состояние: Некоторые из устройств не работают",
            },
            "mbrd": {"Value": "green", "Legend": "ok"},
        },
    },
    "1": {
        "DepotNumber": 6124,
        "VehicleId": 2,
        "Indicators": {
            "summary-state": {"Value": "red", "Legend": "Общее состояние: Критично"},
        },
    },
}


def test_extract_red_issues():
    issues = diagnostic.extract_red_issues(SAMPLE_DATA)
    assert len(issues) == 1  # summary-state игнорируется
    assert issues[0]["depot_number"] == 6123
    assert issues[0]["indicator"] == "brd"
    assert "не работают" in issues[0]["legend"]


def test_extract_red_issues_from_list():
    payload = [
        {
            "DepotNumber": 100,
            "Indicators": {
                "x": {"Value": "red", "Legend": "bad"},
                "y": {"Value": "green", "Legend": "ok"},
                "summary-state": {"Value": "red", "Legend": "ignore"},
            },
        },
        {"DepotNumber": 101, "Indicators": {"z": {"Value": "grey", "Legend": "off"}}},
    ]
    issues = diagnostic.extract_red_issues(payload)
    assert len(issues) == 1  # summary-state не учитывается
    assert issues[0]["depot_number"] == 100
    assert issues[0]["indicator"] == "x"


def test_format_issues_human():
    text = diagnostic.format_issues_compact(
        [{"depot_number": 1234, "indicator": "brd", "legend": "Ошибка\nдлинно"}]
    )
    assert "1234 brd" in text
    assert "Ошибка" in text

    ok_text = diagnostic.format_issues_compact([])
    assert "не обнаружено" in ok_text


def test_fetch_branch_diagnostics(monkeypatch):
    captured = {}

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    class DummySession:
        def post(self, url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            captured["timeout"] = timeout
            return DummyResponse()

    monkeypatch.setattr(diagnostic, "_session", lambda: DummySession())
    monkeypatch.setattr(diagnostic, "_auth_headers", lambda **kwargs: {"auth": "token"})

    monkeypatch.setattr(diagnostic, "UMP_USER_ID", 10, raising=False)

    res = diagnostic.fetch_branch_diagnostics(branch_id=1382, token_path="x")

    assert res == {"ok": True}
    assert captured["json"]["Filters"]["Branchs"] == [1382]
    assert "Page-Id" in captured["headers"]
    assert "db-api-query" in captured["url"]


def test_fetch_branch_requires_user_id(monkeypatch):
    monkeypatch.setattr(diagnostic, "UMP_USER_ID", None, raising=False)
    with pytest.raises(ValueError):
        diagnostic.fetch_branch_diagnostics(branch_id=1, token_path="x")


def test_extract_user_id_from_token():
    # header.payload.signature (payload: {"userId":123})
    sample = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VySWQiOjEyMywidXNlcm5hbWUiOiJ0ZXN0In0.sig"
    assert diagnostic.extract_user_id_from_token(sample) == 123
    assert diagnostic.extract_user_id_from_token("invalid") is None


def test_is_indicator_suppressed():
    data = {"Value": [{"Value": "grey", "Status": "Устройство выключено"}]}
    assert diagnostic.is_indicator_suppressed(data) is True
    data2 = {"Value": [{"Value": "green", "Status": "ok"}]}
    assert diagnostic.is_indicator_suppressed(data2) is False
    data3 = {"Value": [{"Value": "red", "Status": "bad"}]}
    assert diagnostic.is_indicator_suppressed(data3) is False

