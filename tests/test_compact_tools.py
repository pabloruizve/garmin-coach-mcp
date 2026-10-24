"""Tests de las 4 tools de análisis compacto (zonas, resumen semanal, deriva, carreras comparables). Sin red."""
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
    spec = importlib.util.spec_from_file_location("server_compact", SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server_compact"] = mod
    spec.loader.exec_module(mod)
    return mod


def _fn(tool):
    return getattr(tool, "fn", tool)


def _act(aid, day, km=10.0, mins=55.0, hr=148, name="Rodaje", te=3.0, ana=0.5, label="BASE", load=100.0):
    return {
        "activityId": aid, "activityName": name, "startTimeLocal": f"{day} 08:00:00",
        "activityType": {"typeId": 1, "typeKey": "Correr"},
        "distance": km * 1000, "duration": mins * 60, "averageSpeed": km * 1000 / (mins * 60),
        "averageHR": hr, "aerobicTrainingEffect": te, "anaerobicTrainingEffect": ana,
        "trainingEffectLabel": label, "activityTrainingLoad": load,
    }


class FakeApi:
    def __init__(self, acts, items=None):
        self.acts, self.items = acts, items or []

    def get_activities_by_date(self, start, end, *a, **k):
        return [x for x in self.acts if start <= x["startTimeLocal"][:10] <= end]

    def get_scheduled_workouts(self, y, m):
        return {"calendarItems": self.items}


def _recs(hrs, speed=3.0):
    return [(float(i), h, speed) for i, h in enumerate(hrs)]


def test_zone_seconds_boundaries(srv):
    recs = _recs([139, 140, 165, 166])
    z = srv._ca_zone_seconds(recs, 140, 165)
    assert z["Z1"] == 1 and z["Z2"] == 2 and z["Z3"] == 1


def test_zone_seconds_caps_pauses(srv):
    recs = [(0.0, 120, 3.0), (1000.0, 120, 3.0)]
    assert srv._ca_zone_seconds(recs, 140, 165)["Z1"] == 11.0


def test_get_time_in_zones(srv, monkeypatch):
    acts = [_act(1, "2026-10-20"), _act(2, "2026-10-22")]
    monkeypatch.setattr(srv, "_get_api", lambda: FakeApi(acts))
    data = {1: _recs([130] * 80 + [150] * 20), 2: _recs([130] * 100)}
    monkeypatch.setattr(srv, "_ca_records", lambda aid: data[aid])
    r = _fn(srv.get_time_in_zones)("2026-10-19", "2026-10-25")
    assert r["activities"] == 2
    assert r["total_pct"]["Z1"] == pytest.approx(90.0, abs=1)
    assert r["total_pct"]["Z2"] == pytest.approx(10.0, abs=1)
    assert r["vs_objetivo"]["Z1"] == "por_encima" and r["vs_objetivo"]["Z3"] == "por_debajo"
    assert len(r["per_activity"]) == 2


def test_time_in_zones_validations(srv, monkeypatch):
    monkeypatch.setattr(srv, "_get_api", lambda: FakeApi([]))
    with pytest.raises(ValueError):
        _fn(srv.get_time_in_zones)("2026-10-01", "2026-10-02", z1_upper=170, z2_upper=165)
    with pytest.raises(RuntimeError):
        _fn(srv.get_time_in_zones)("2026-10-01", "2026-10-02")


def test_time_in_zones_reports_fit_errors(srv, monkeypatch):
    monkeypatch.setattr(srv, "_get_api", lambda: FakeApi([_act(1, "2026-10-20"), _act(2, "2026-10-21")]))

    def rec(aid):
        if aid == 1:
            raise RuntimeError("sin FIT")
        return _recs([150] * 60)

    monkeypatch.setattr(srv, "_ca_records", rec)
    r = _fn(srv.get_time_in_zones)("2026-10-19", "2026-10-25")
    assert r["activities"] == 1 and r["errors"][0]["activity_id"] == 1
    assert r["total_pct"]["Z2"] == 100.0


def test_weekly_summary(srv, monkeypatch):
    acts = [
        _act(1, "2026-10-20", name="Rodaje", te=2.8, ana=0.0, label="BASE", load=80),
        _act(2, "2026-10-21", name="Series", te=4.2, ana=1.0, label="VO2MAX", load=150),
        _act(3, "2026-10-24", name="Tempo", te=3.9, ana=0.5, label="TEMPO", load=120),
        {**_act(4, "2026-10-23"), "activityType": {"typeId": 2, "typeKey": "Ciclismo"}},
    ]
    items = [
        {"itemType": "Entrenamiento", "date": "2026-10-20", "title": "Rodaje", "workoutId": 1},
        {"itemType": "Entrenamiento", "date": "2026-10-24", "title": "Rodaje 10K", "workoutId": 4},
        {"itemType": "Entrenamiento", "date": "2026-10-22", "title": "Tempo", "workoutId": 2},
        {"itemType": "activity", "date": "2026-10-24", "title": "Tempo", "workoutId": 3},
    ]
    monkeypatch.setattr(srv, "_get_api", lambda: FakeApi(acts, items))
    r = _fn(srv.get_weekly_summary)("2026-10-22")
    w = r["weeks"][0]
    assert w["week_start"] == "2026-10-19" and w["week_end"] == "2026-10-25"
    # el 24 Garmin dice TEMPO pero estaba planificado un rodaje: nunca cuenta como dura
    assert w["sessions"] == 3 and w["hard_sessions"] == 1
    assert w["hard_dates"] == ["2026-10-21"] and w["min_days_between_hard"] is None
    assert [s for s in w["per_session"] if s["date"] == "2026-10-24"][0]["garmin_says_hard"] is True
    assert w["load"] == 350.0
    assert "2026-10-23" in w["rest_days"]
    pv = {p["date"]: p for p in w["planned_vs_executed"]}
    assert pv["2026-10-20"]["done"] is True and pv["2026-10-22"]["done"] is False
    assert pv["2026-10-24"]["done"] is True and "2026-10-21" in w["unplanned_executed"]


def test_weekly_summary_validates_weeks(srv):
    with pytest.raises(ValueError):
        _fn(srv.get_weekly_summary)(weeks=13)


def test_cardiac_drift(srv, monkeypatch):
    recs = [(float(i), 140, 3.0) for i in range(600)] + [(float(600 + i), 154, 3.0) for i in range(600)]
    monkeypatch.setattr(srv, "_ca_records", lambda aid: recs)
    r = _fn(srv.get_cardiac_drift)("123", skip_warmup_pct=0)
    assert r["hr_change_bpm"] == 14.0
    assert r["drift_pct"] == pytest.approx(9.1, abs=0.2)
    assert r["banda"].startswith("moderada")


def test_cardiac_drift_few_records(srv, monkeypatch):
    monkeypatch.setattr(srv, "_ca_records", lambda aid: _recs([140] * 30))
    with pytest.raises(RuntimeError):
        _fn(srv.get_cardiac_drift)("123")
    with pytest.raises(ValueError):
        _fn(srv.get_cardiac_drift)("123", skip_warmup_pct=90)


def test_comparable_runs(srv, monkeypatch):
    acts = [
        _act(1, "2026-08-01", km=10, mins=60, hr=152),
        _act(2, "2026-09-01", km=10, mins=58, hr=150),
        _act(3, "2026-10-01", km=10, mins=56, hr=148),
        _act(4, "2026-10-05", km=21, mins=120, hr=160),  # fuera de franja
        _act(5, "2026-10-10", km=10, mins=50, hr=175, name="Series"),  # fuera por FC
    ]
    monkeypatch.setattr(srv, "_get_api", lambda: FakeApi(acts))
    r = _fn(srv.get_comparable_runs)("2026-08-01", "2026-10-31", max_avg_hr=160)
    assert r["n"] == 3
    assert r["ef_change_pct"] > 0 and r["ef_slope_pct_per_30d"] > 0
    assert r["first_third"]["pace"] == "6:00" and r["last_third"]["pace"] == "5:36"
    assert all("_spd" not in x for x in r["runs"])
    r2 = _fn(srv.get_comparable_runs)("2026-08-01", "2026-10-31", name_contains="series", max_km=12)
    assert r2["n"] == 1
    with pytest.raises(RuntimeError):
        _fn(srv.get_comparable_runs)("2026-08-01", "2026-10-31", name_contains="nada")
