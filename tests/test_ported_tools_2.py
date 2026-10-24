"""Segunda tanda de tools portadas de Taxuspt/garmin_mcp, con un cliente Garmin falso (sin red)."""
import asyncio
import importlib.util
import os
import sys
from datetime import datetime

import pytest

os.environ.setdefault("GARMIN_EMAIL", "x@x")
os.environ.setdefault("GARMIN_PASSWORD", "x")
os.environ["GARMIN_LANGUAGE"] = "es"
SERVER = os.path.join(os.path.dirname(__file__), "..", "server.py")


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("server_ported2_under_test", SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server_ported2_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _fn(tool):
    return getattr(tool, "fn", tool)


class FakeClient:
    def __init__(self):
        self.puts = []

    def put(self, kind, url, **kwargs):
        self.puts.append((kind, url, kwargs))
        return {}


class FakeApi:
    garmin_connect_activity = "/activity-service/activity"
    garmin_connect_activities = "/activitylist-service/activities/search/activities"

    def __init__(self):
        self.client = FakeClient()
        self.calls = []
        self.readiness = None
        self.morning = None
        self.activities = []
        self.detail_error = None

    def connectapi(self, path, **kw):
        self.calls.append((path, kw))
        if path.startswith("/usersummary-service/stats/daily/"):
            if kw["params"]["statsType"] == "CALORIES":
                return {"values": [{"calendarDate": "2026-10-20", "values": {"totalCalories": 2500, "activeCalories": 700, "restingCalories": 1800}}]}
            return {"values": [{"calendarDate": "2026-10-20", "values": {"totalSteps": 9000}}]}
        if path.startswith("/calendar-service/event/"):
            return {"eventCustomization": {"customGoal": {"unitType": "time", "unit": "second", "value": 5400}}}
        if path == self.garmin_connect_activities:
            return [{"activityId": 7, "aerobicTrainingEffect": 4.1, "anaerobicTrainingEffect": 0.0, "recoveryTime": 1500}]
        raise AssertionError(path)

    # lecturas
    def get_morning_training_readiness(self, d):
        return self.morning

    def get_training_readiness(self, d):
        return self.readiness

    def get_activities(self, a, b):
        return self.activities

    def get_scheduled_workouts(self, y, m):
        return {"calendarItems": [
            {"itemType": "event", "title": "Media de Madrid", "date": "2026-10-25", "isRace": True, "primaryEvent": True, "id": 55,
             "completionTarget": {"unitType": "distance", "unit": "kilometer", "value": 21.0975},
             "eventTimeLocal": {"startTimeHhMm": "09:00", "timeZoneId": "Europe/Madrid"}, "location": "  Madrid "},
            {"itemType": "workout", "title": "Rodaje", "date": "2026-10-26"},
            {"itemType": "event", "title": "Fuera de rango", "date": "2026-10-31"},
        ]}

    def get_respiration_data(self, d):
        if d == "2026-10-21":
            return {}
        return {"avgWakingRespirationValue": 14.04, "avgSleepRespirationValue": 12.5, "highestRespirationValue": 20, "lowestRespirationValue": 9}

    def get_lactate_threshold(self, **kw):
        if kw.get("latest"):
            return {"speed_and_heart_rate": {"speed": 0.3888878, "heartRate": 168, "calendarDate": "2026-10-01"}, "power": {}}
        return {"speed": [{"from": "2026-10-01", "value": 0.38, "series": "RUNNING"}], "heart_rate": [{"from": "2026-10-01", "value": 167}]}

    def get_activity(self, aid):
        if self.detail_error:
            raise RuntimeError(self.detail_error)
        return {"summaryDTO": {"trainingEffect": 3.7, "anaerobicTrainingEffect": 0.2, "trainingEffectLabel": "BASE", "recoveryTime": 900, "activityTrainingLoad": 166.9}}

    def get_sleep_data(self, d):
        if d == "2026-10-21":
            return {}
        return {"dailySleepDTO": {"sleepTimeSeconds": 27000, "sleepScores": {"overall": {"value": 81, "qualifierKey": "GOOD"}}, "deepSleepSeconds": 5000},
                "restingHeartRate": 52, "avgOvernightHrv": 61}

    def get_activity_types(self):
        # Tu cuenta devuelve typeKey localizados
        return [{"typeId": 1, "typeKey": "Correr", "parentTypeId": 17}, {"typeId": 6, "typeKey": "Trail running", "parentTypeId": 1}]

    def get_scheduled_workout_by_id(self, sid):
        return {"scheduledWorkoutId": sid, "calendarDate": "2026-10-27", "workout": {"workoutId": 9, "workoutName": "Tempo", "estimatedDuration": 3600}}

    # escrituras
    def add_gear_to_activity(self, uuid, aid):
        if uuid == "missing":
            raise RuntimeError("Gear doesn't exist")
        self.calls.append(("add_gear", uuid, aid))

    def remove_gear_from_activity(self, uuid, aid):
        self.calls.append(("remove_gear", uuid, aid))

    def set_activity_type(self, aid, tid, key, parent):
        self.calls.append(("set_type", aid, tid, key, parent))


@pytest.fixture
def api(srv, monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(srv, "_get_api", lambda: fake)
    return fake


def test_registered_in_mcp(srv):
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert {"get_morning_training_readiness", "get_recovery_time_remaining", "get_calendar_events", "get_respiration_trend",
            "get_lactate_threshold", "get_training_effect", "get_sleep_summary_range", "get_stats_range",
            "add_gear_to_activity", "remove_gear_from_activity", "set_activity_type", "reschedule_workout"} <= names


def test_morning_readiness_empty_is_clear_error(srv, api):
    with pytest.raises(RuntimeError, match="matinal"):
        _fn(srv.get_morning_training_readiness)("2026-10-24")
    api.morning = {"score": 70}
    assert _fn(srv.get_morning_training_readiness)("2026-10-24")["morning_training_readiness"] == {"score": 70}


def test_recovery_prefers_readiness_snapshot(srv, api):
    api.readiness = [{"calendarDate": "2026-10-24", "timestampLocal": "2026-10-24T07:00:00", "recoveryTime": 1800, "score": 55}]
    out = _fn(srv.get_recovery_time_remaining)("2026-10-24")
    assert out["remaining_hours"] == 30.0 and out["state"] == "sin_recuperar" and out["value_type"] == "snapshot"


def test_recovery_reached_zero(srv, api):
    api.readiness = {"timestampLocal": "t", "recoveryTime": 600, "recoveryTimeChangePhrase": "REACHED_ZERO"}
    out = _fn(srv.get_recovery_time_remaining)("2026-10-24")
    assert out["remaining_hours"] == 0.0 and out["state"] == "recuperado"


def test_recovery_estimate_from_activities_today_only(srv, api, monkeypatch):
    now = datetime(2026, 10, 24, 13, 0, tzinfo=srv.APP_TIMEZONE)
    monkeypatch.setattr(srv, "_now_local", lambda: now)
    start = datetime(2026, 10, 24, 10, 7, tzinfo=srv.APP_TIMEZONE)
    api.activities = [{"activityId": 1, "activityName": "Rodaje 10K", "recoveryTime": 1500, "duration": 3500, "beginTimestamp": start.timestamp() * 1000}]
    out = _fn(srv.get_recovery_time_remaining)("2026-10-24")
    assert out["value_type"] == "estimate" and out["source"] == "recent_activity"
    assert 20 < out["remaining_hours"] < 25
    past = _fn(srv.get_recovery_time_remaining)("2026-10-20")
    assert past["remaining_hours"] is None and past["state"] == "no_disponible"


def test_calendar_events_filters_and_curates(srv, api):
    out = _fn(srv.get_calendar_events)("2026-10-24", "2026-10-30")
    assert out["count"] == 1
    ev = out["events"][0]
    assert ev["title"] == "Media de Madrid" and ev["primary_event"] is True
    assert ev["distance_meters"] == pytest.approx(21097.5)
    assert ev["goal_time_seconds"] == 5400.0 and ev["location"] == "Madrid" and ev["start_time_local"] == "09:00"
    with pytest.raises(ValueError):
        _fn(srv.get_calendar_events)("2026-10-30", "2026-10-24")


def test_respiration_trend_skips_empty_days(srv, api):
    out = _fn(srv.get_respiration_trend)("2026-10-20", "2026-10-22")
    assert out["days_with_data"] == 2 and out["trend"][0]["avg_waking_breaths_per_min"] == 14.0
    assert out["period_avg_sleep_breaths_per_min"] == 12.5
    with pytest.raises(ValueError):
        _fn(srv.get_respiration_trend)("2026-01-01", "2026-03-01")


def test_lactate_threshold_latest_and_range(srv, api):
    out = _fn(srv.get_lactate_threshold)()
    assert out["lactate_threshold_speed_mps"] == pytest.approx(3.889, abs=1e-3) and out["lactate_threshold_heart_rate_bpm"] == 168
    rng = _fn(srv.get_lactate_threshold)("2026-09-01", "2026-10-24")
    assert rng["speed_history"][0]["speed_mps"] == pytest.approx(3.8) and rng["heart_rate_history"][0]["heart_rate_bpm"] == 167
    with pytest.raises(ValueError):
        _fn(srv.get_lactate_threshold)("2026-09-01")


def test_training_effect_details_and_403_fallback(srv, api):
    out = _fn(srv.get_training_effect)("7")
    assert out["source"] == "activity_details" and out["aerobic_effect"] == 3.7 and out["recovery_time_hours"] == 15.0 and out["training_load"] == 166.9
    api.detail_error = "HTTP 403 Forbidden"
    fb = _fn(srv.get_training_effect)("7")
    assert fb["source"] == "activity_list" and fb["aerobic_effect"] == 4.1 and fb["recovery_time_hours"] == 25.0
    api.detail_error = "boom"
    with pytest.raises(RuntimeError, match="boom"):
        _fn(srv.get_training_effect)("7")


def test_sleep_summary_range(srv, api):
    out = _fn(srv.get_sleep_summary_range)("2026-10-20", "2026-10-22")
    assert out["nights_requested"] == 3 and out["nights_returned"] == 2
    n = out["nights"][0]
    assert n["sleep_hours"] == 7.5 and n["sleep_score"] == 81 and n["resting_heart_rate_bpm"] == 52 and n["avg_overnight_hrv"] == 61


def test_stats_range_marks_missing_days_not_zero(srv, api):
    out = _fn(srv.get_stats_range)("2026-10-20", "2026-10-21")
    d0, d1 = out["days"]
    assert d0["total_calories"] == 2500 and d0["steps"] == 9000 and d0["has_data"] is True
    assert d1["has_data"] is False and d1["total_calories"] is None and d1["steps"] is None
    with pytest.raises(ValueError):
        _fn(srv.get_stats_range)("2026-01-01", "2026-03-01")


def test_gear_add_remove_and_missing(srv, api):
    assert _fn(srv.add_gear_to_activity)("5", "uuid-1")["ok"]
    assert _fn(srv.remove_gear_from_activity)("5", "uuid-1")["ok"]
    assert ("add_gear", "uuid-1", 5) in api.calls and ("remove_gear", "uuid-1", 5) in api.calls
    with pytest.raises(RuntimeError, match="no existe"):
        _fn(srv.add_gear_to_activity)("5", "missing")


def test_set_activity_type_accepts_localized_key_id_and_english_alias(srv, api):
    assert _fn(srv.set_activity_type)("5", "Correr")["type_id"] == 1
    assert _fn(srv.set_activity_type)("5", "trail running")["type_id"] == 6
    assert _fn(srv.set_activity_type)("5", "6")["type_id"] == 6
    out = _fn(srv.set_activity_type)("5", "running")
    assert out["type_id"] == 1 and out["type_key"] == "Correr"
    assert ("set_type", 5, 1, "Correr", 17) in api.calls
    with pytest.raises(ValueError, match="Correr"):
        _fn(srv.set_activity_type)("5", "nada")


def test_reschedule_workout_sends_workout_reference_only(srv, api, monkeypatch):
    sent = []
    monkeypatch.setattr(srv, "_garmin_transport_call", lambda a, m, p, **kw: sent.append((m, p, kw)) or {})
    out = _fn(srv.reschedule_workout)(321, "2026-10-29")
    assert out == {"ok": True, "scheduled_workout_id": 321, "previous_date": "2026-10-27", "calendar_date": "2026-10-29"}
    m, p, kw = sent[0]
    assert m == "put" and p == "workout-service/schedule/321"
    assert kw["json"]["calendarDate"] == "2026-10-29" and kw["json"]["workout"] == {"workoutId": 9}
    with pytest.raises(ValueError):
        _fn(srv.reschedule_workout)(321, "29-10-2026")


def test_new_writes_can_be_disabled(srv, api, monkeypatch):
    monkeypatch.setattr(srv, "_PORTED_WRITES_DISABLED", True)
    for call in (
        lambda: _fn(srv.add_gear_to_activity)("5", "u"),
        lambda: _fn(srv.remove_gear_from_activity)("5", "u"),
        lambda: _fn(srv.set_activity_type)("5", "running"),
        lambda: _fn(srv.reschedule_workout)(1, "2026-10-29"),
    ):
        with pytest.raises(RuntimeError, match="desactivadas"):
            call()
    assert not [c for c in api.calls if c[0] in ("add_gear", "remove_gear", "set_type")]
