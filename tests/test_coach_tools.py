"""Pruebas de las tools compactas de coach, con un cliente Garmin falso (sin red)."""
import importlib.util
import io
import os
import sys
import types
import zipfile
from datetime import date

import pytest

os.environ.setdefault("GARMIN_EMAIL", "x@x")
os.environ.setdefault("GARMIN_PASSWORD", "x")
os.environ["GARMIN_LANGUAGE"] = "es"
SERVER = os.path.join(os.path.dirname(__file__), "..", "server.py")


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("server_under_test", SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _fn(tool):
    return getattr(tool, "fn", tool)


class FakeApi:
    def __init__(self):
        self.calls = []

    def get_scheduled_workouts(self, y, m):
        self.calls.append((y, m))
        items = {
            (2026, 10): [
                {"itemType": "Entrenamiento", "date": "2026-10-07", "title": "4K Cto + 8x1000 (4:30)", "workoutId": 11, "id": 99, "sportTypeKey": "running", "completed": False},
                {"itemType": "Entrenamiento", "date": "2026-10-07", "title": "4K Cto + 8x1000 (4:30)", "workoutId": 11, "id": 99, "sportTypeKey": "running"},  # duplicado
                {"itemType": "activity", "date": "2026-10-03", "title": "Rodaje", "id": 5, "activityTypeId": 1, "distance": 1001115, "duration": 3300000, "averageHR": 144},
                {"itemType": "goal", "date": "2026-10-01", "title": "Running octubre 2026", "id": 3},
                {"itemType": "nap", "date": "2026-10-02", "id": None, "duration": 4860},
                {"itemType": "Entrenamiento", "date": "2026-10-31", "title": "fuera de rango", "workoutId": 1, "id": 1},
            ],
            (2026, 9): [{"itemType": "Entrenamiento", "date": "2026-09-30", "title": "Rodaje 10K", "workoutId": 7, "id": 8}],
        }
        return {"calendarItems": items.get((y, m), [])}

    def get_workout_by_id(self, wid):
        return {
            "workoutName": "4K Cto + 7K (4:55) + 2K Soltar",
            "sportType": {"sportTypeKey": "running"},
            "estimatedDurationInSecs": 4600,
            "workoutSegments": [{"workoutSteps": [
                {"stepType": {"stepTypeKey": "warmup"}, "endCondition": {"conditionTypeKey": "distance"}, "endConditionValue": 4000, "targetType": {"workoutTargetTypeKey": "no.target"}},
                {"stepType": {"stepTypeKey": "interval"}, "endCondition": {"conditionTypeKey": "distance"}, "endConditionValue": 7000,
                 "targetType": {"workoutTargetTypeKey": "pace.zone"}, "targetValueOne": 3.4482759, "targetValueTwo": 3.3333333},
                {"type": "RepeatGroupDTO", "numberOfIterations": 3, "workoutSteps": [
                    {"stepType": {"stepTypeKey": "rest"}, "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 60, "targetType": {"workoutTargetTypeKey": "no.target"}}]},
            ]}],
        }

    def get_training_status(self, day):
        if day == "2026-10-02":
            return None
        v = {"2026-10-01": 50.0, "2026-10-03": 50.0, "2026-10-04": 51.0}.get(day, 50.0)
        return {
            "mostRecentVO2Max": {"generic": {"vo2MaxValue": v}},
            "mostRecentTrainingStatus": {"latestTrainingStatusData": {"d1": {
                "primaryTrainingDevice": True,
                "trainingStatusFeedbackPhrase": "PRODUCTIVE_1",
                "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 400.0, "dailyTrainingLoadChronic": 450.0,
                                         "dailyAcuteChronicWorkloadRatio": 0.9, "acwrStatus": "OPTIMAL"}}}},
        }


@pytest.fixture
def api(srv, monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(srv, "_get_api", lambda: fake)
    return fake


def test_calendar_range_compact_dedup_and_months(srv, api):
    r = _fn(srv.get_calendar_range)("2026-09-30", "2026-10-15")
    assert api.calls == [(2026, 9), (2026, 10)]
    assert [i["date"] for i in r["items"]] == ["2026-09-30", "2026-10-07"]
    assert r["count"] == 2  # sin duplicado, sin actividad, sin fuera de rango
    assert r["items"][1]["workout_id"] == 11 and r["items"][1]["scheduled_workout_id"] == 99
    # sin traducir: filtros por type == "workout" deben funcionar
    assert r["items"][1]["type"] == "workout"


def test_calendar_range_with_activities(srv, api):
    r = _fn(srv.get_calendar_range)("2026-10-01", "2026-10-10", include_activities=True)
    act = [i for i in r["items"] if i["type"] == "activity"][0]
    assert act["distance_km"] == 10.01 and act["duration_min"] == 55.0 and act["avg_hr"] == 144 and act["activity_type_id"] == 1
    assert not [i for i in r["items"] if i["type"] in ("goal", "nap")]


def test_calendar_range_validation(srv, api):
    with pytest.raises(ValueError):
        _fn(srv.get_calendar_range)("2026-10-10", "2026-10-01")
    with pytest.raises(ValueError):
        _fn(srv.get_calendar_range)("2026-01-01", "2026-12-31")


def test_workout_compact_pace_and_repeat(srv, api):
    w = _fn(srv.get_workout_compact)("1")
    s = w["steps"]
    assert s[0] == {"type": "warmup", "distance_m": 4000, "target": "no.target"}
    assert (s[1]["pace_fast"], s[1]["pace_slow"]) == ("4:50", "5:00")
    assert s[2]["type"] == "repeat" and s[2]["iterations"] == 3 and s[2]["steps"][0]["duration_s"] == 60


def test_training_load_trend(srv, api):
    r = _fn(srv.get_training_load_trend)("2026-10-01", "2026-10-04")
    assert r["days_with_data"] == 3  # el 2 no tiene datos
    assert r["trend"][0]["tsb"] == 50.0 and r["trend"][0]["acwr"] == 0.9
    assert "vo2_max" not in r["trend"][0]


def test_vo2max_trend_carried_forward(srv, api):
    r = _fn(srv.get_vo2max_trend)("2026-10-01", "2026-10-04")
    assert [t["carried_forward"] for t in r["trend"]] == [False, True, False]
    assert r["change"] == 1.0


def _make_fit(tmp_path):
    from fitparse import FitFile  # noqa: F401  (comprueba que está instalado)
    return None


def test_fit_messages_bytes_helpers(srv):
    raw = b"\x0e\x10fakefit"
    assert srv._coach_fit_bytes(raw) == raw
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.fit", b"INNER")
    assert srv._coach_fit_bytes(buf.getvalue()) == b"INNER"
    assert srv._coach_fit_value(date(2026, 10, 4)) == "2026-10-04"
    assert srv._coach_fit_value(b"\x01\xff") == "01ff"


def test_fit_messages_validates_args(srv, api):
    with pytest.raises(ValueError):
        _fn(srv.get_activity_fit_messages)("1", message_limit=0)


class _F:
    def __init__(self, name, value, units=None):
        self.name, self.value, self.units = name, value, units


class _M:
    def __init__(self, name, fields):
        self.name, self.fields = name, fields


def test_fit_fields_drop_nulls_and_map_intensity(srv):
    m = _M("workout_step", [
        _F("duration_time", 30, "s"), _F("notes", None), _F("intensity", 4),
        _F("pool_length", None, "m"), _F("target_type", "open"),
    ])
    assert srv._coach_fit_fields(m) == {"duration_time": {"value": 30, "units": "s"}, "intensity": "recovery", "target_type": "open"}
    assert "notes" in srv._coach_fit_fields(m, include_nulls=True)
    # un intensity ya textual no se toca, y solo se mapea en workout_step
    assert srv._coach_fit_fields(_M("workout_step", [_F("intensity", "warmup")]))["intensity"] == "warmup"
    assert srv._coach_fit_fields(_M("lap", [_F("intensity", 4)]))["intensity"] == 4


def test_translation_opt_out_only_for_structural_tools(srv, api):
    wc = _fn(srv.get_workout_compact)("1")
    assert wc["sport"] == "running"  # no traducido a "Correr"
    tl = _fn(srv.get_training_load_trend)("2026-10-01", "2026-10-01")
    assert tl["trend"][0]["acwr_status"] == "Óptimo"  # las demás siguen traduciéndose
