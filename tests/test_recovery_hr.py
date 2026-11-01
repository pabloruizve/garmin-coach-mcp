"""Tests de get_recovery_hr y get_recovery_hr_trend. Sin red."""
import importlib.util
import os
import sys

import pytest

os.environ.setdefault("GARMIN_EMAIL", "x@x")
os.environ.setdefault("GARMIN_PASSWORD", "x")
os.environ["GARMIN_LANGUAGE"] = "es"
SERVER = os.path.join(os.path.dirname(__file__), "..", "server.py")


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("server_recovery", SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server_recovery"] = mod
    spec.loader.exec_module(mod)
    return mod


def _fn(tool):
    return getattr(tool, "fn", tool)


def _listed(aid, day):
    return {"activityId": aid, "startTimeLocal": f"{day} 08:00:00"}


def _detail(aid, day, rec, km=14.0):
    summary = {"distance": km * 1000, "startTimeLocal": f"{day} 08:00:00", "averageHR": 143, "maxHR": 160}
    if rec is not None:
        summary["recoveryHeartRate"] = rec
    return {"activityId": aid, "activityName": f"Rodaje {aid}", "summaryDTO": summary}


class FakeApi:
    def __init__(self, acts, details, laps=None):
        self.acts, self.details, self.laps = acts, details, laps or {}
        self.detail_calls = []
        self.split_calls = []

    def get_activities_by_date(self, start, end, *a, **k):
        return [x for x in self.acts if start <= x["startTimeLocal"][:10] <= end]

    def get_activity(self, aid):
        self.detail_calls.append(str(aid))
        return self.details[str(aid)]

    def get_activity_splits(self, aid):
        self.split_calls.append(str(aid))
        return {"lapDTOs": self.laps.get(str(aid), [])}


def _api():
    acts = [_listed(3, "2026-11-01"), _listed(1, "2026-09-27"), _listed(2, "2026-10-11")]
    details = {
        "1": _detail(1, "2026-09-27", 35),
        "2": _detail(2, "2026-10-11", 31),
        "3": _detail(3, "2026-11-01", 28),
    }
    laps = {"3": [{"averageHR": 140, "duration": 300.0}, {"averageHR": 136.0, "duration": 62.5}]}
    return FakeApi(acts, details, laps)


def test_get_recovery_hr_rows_and_end_hr(srv, monkeypatch):
    api = _api()
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    r = _fn(srv.get_recovery_hr)(["3", "1"])
    assert r["count"] == 2
    a, b = r["activities"]
    assert a["recovery_hr"] == 28 and a["distance_km"] == 14.0 and a["date"] == "2026-11-01"
    assert a["last_lap_avg_hr"] == 136.0 and a["last_lap_s"] == 62.5
    assert b["recovery_hr"] == 35 and b["last_lap_avg_hr"] is None


def test_get_recovery_hr_skips_splits_when_disabled(srv, monkeypatch):
    api = _api()
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    r = _fn(srv.get_recovery_hr)(["1"], include_end_hr=False)
    assert "last_lap_avg_hr" not in r["activities"][0]
    assert api.split_calls == []


def test_get_recovery_hr_null_when_missing(srv, monkeypatch):
    api = FakeApi([], {"9": _detail(9, "2026-10-01", None)})
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    r = _fn(srv.get_recovery_hr)(["9"], include_end_hr=False)
    assert r["activities"][0]["recovery_hr"] is None


def test_get_recovery_hr_validations(srv, monkeypatch):
    monkeypatch.setattr(srv, "_get_api", lambda: _api())
    with pytest.raises(ValueError):
        _fn(srv.get_recovery_hr)([])
    with pytest.raises(ValueError):
        _fn(srv.get_recovery_hr)([str(i) for i in range(11)])


def test_get_recovery_hr_reports_per_activity_error(srv, monkeypatch):
    class Boom(FakeApi):
        def get_activity(self, aid):
            raise RuntimeError("fallo")

    monkeypatch.setattr(srv, "_get_api", lambda: Boom([], {}))
    r = _fn(srv.get_recovery_hr)(["1"], include_end_hr=False)
    assert "error" in r["activities"][0]


def test_trend_sorted_and_mean(srv, monkeypatch):
    monkeypatch.setattr(srv, "_get_api", lambda: _api())
    r = _fn(srv.get_recovery_hr_trend)("2026-09-01", "2026-11-01")
    assert [x["activity_id"] for x in r["activities"]] == ["1", "2", "3"]
    assert r["count"] == 3 and r["with_recovery_hr"] == 3
    assert r["mean_recovery_hr"] == pytest.approx(31.3, abs=0.05)
    assert r["truncated"] is False


def test_trend_max_activities_keeps_most_recent(srv, monkeypatch):
    api = _api()
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    r = _fn(srv.get_recovery_hr_trend)("2026-09-01", "2026-11-01", max_activities=2)
    assert [x["activity_id"] for x in r["activities"]] == ["2", "3"]
    assert r["truncated"] is True
    assert sorted(api.detail_calls) == ["2", "3"]


def test_trend_ignores_missing_values_in_mean(srv, monkeypatch):
    api = _api()
    api.details["2"] = _detail(2, "2026-10-11", None)
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    r = _fn(srv.get_recovery_hr_trend)("2026-09-01", "2026-11-01")
    assert r["with_recovery_hr"] == 2 and r["mean_recovery_hr"] == 31.5


def test_trend_validations_and_empty(srv, monkeypatch):
    monkeypatch.setattr(srv, "_get_api", lambda: _api())
    with pytest.raises(ValueError):
        _fn(srv.get_recovery_hr_trend)("2026-09-01", max_activities=0)
    r = _fn(srv.get_recovery_hr_trend)("2025-01-01", "2025-01-31")
    assert r["count"] == 0 and r["mean_recovery_hr"] is None


def test_hr_at_2min_reliable_short_last_lap(srv, monkeypatch):
    api = _api()
    api.laps["3"] = [{"averageHR": 140, "duration": 300.0}, {"averageHR": 136.0, "duration": 4.0}]
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    a = _fn(srv.get_recovery_hr)(["3"])["activities"][0]
    assert a["end_hr_reliable"] is True and a["hr_at_2min"] == 108


def test_hr_at_2min_null_when_last_lap_long(srv, monkeypatch):
    monkeypatch.setattr(srv, "_get_api", lambda: _api())  # activity 3: última vuelta de 62,5 s
    a = _fn(srv.get_recovery_hr)(["3"])["activities"][0]
    assert a["end_hr_reliable"] is False and a["hr_at_2min"] is None


def test_hr_at_2min_boundary_30s_is_reliable(srv, monkeypatch):
    api = _api()
    api.laps["3"] = [{"averageHR": 140, "duration": 30.0}]
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    assert _fn(srv.get_recovery_hr)(["3"])["activities"][0]["hr_at_2min"] == 112


def test_hr_at_2min_null_without_recovery_or_laps(srv, monkeypatch):
    api = FakeApi([], {"9": _detail(9, "2026-10-01", None), "8": _detail(8, "2026-10-01", 30)},
                  {"9": [{"averageHR": 150, "duration": 2.0}]})
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    rows = _fn(srv.get_recovery_hr)(["9", "8"])["activities"]
    assert rows[0]["end_hr_reliable"] is True and rows[0]["hr_at_2min"] is None
    assert rows[1]["end_hr_reliable"] is False and rows[1]["hr_at_2min"] is None


def test_trend_includes_hr_at_2min(srv, monkeypatch):
    api = _api()
    api.laps["1"] = [{"averageHR": 147.0, "duration": 2.7}]
    monkeypatch.setattr(srv, "_get_api", lambda: api)
    r = _fn(srv.get_recovery_hr_trend)("2026-09-01", "2026-09-30", include_end_hr=True)
    assert r["activities"][0]["hr_at_2min"] == 112
