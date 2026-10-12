"""Pruebas de las tools portadas de Taxuspt/garmin_mcp, con un cliente Garmin falso (sin red)."""
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
    spec = importlib.util.spec_from_file_location("server_ported_under_test", SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["server_ported_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _fn(tool):
    return getattr(tool, "fn", tool)


class FakeClient:
    def __init__(self):
        self.puts = []
        self.posts = []

    def put(self, kind, url, **kwargs):
        self.puts.append((kind, url, kwargs))
        return {}

    def post(self, kind, url, **kwargs):
        self.posts.append((kind, url, kwargs))
        return {}


class FakeApi:
    garmin_connect_activity = "/activity-service/activity"

    def __init__(self):
        self.client = FakeClient()
        self.scheduled = []
        self.unscheduled = []
        self.deleted = []

    # --- lecturas ---
    def connectapi(self, path, **kwargs):
        assert path == "/biometric-service/heartRateZones"
        return [
            {"sport": "DEFAULT", "maxHeartRateUsed": 186, "zone1Floor": 93},
            {"sport": "RUNNING", "maxHeartRateUsed": 186, "lactateThresholdHeartRateUsed": 164, "zone1Floor": 112},
        ]

    def get_weekly_intensity_minutes(self, start, end):
        return [
            {"calendarDate": "2026-09-14", "weeklyGoal": 150, "moderateValue": 30, "vigorousValue": 60},
            {"calendarDate": "2026-09-21", "weeklyGoal": 150, "moderateValue": None, "vigorousValue": None},
        ]

    def get_running_tolerance(self, start, end, aggregation="weekly"):
        return [
            {"calendarDate": "2026-09-28", "tolerance": 60000, "totalImpactLoad": 45000, "totalDistance": 40000, "startOfWeek": "2026-09-28", "weekIndex": 2},
            {"calendarDate": "2026-09-21", "tolerance": 55000, "totalImpactLoad": 30000, "totalDistance": 30000, "startOfWeek": "2026-09-21", "weekIndex": 1},
        ]

    def get_hrv_data(self, day):
        if day == "2026-10-02":
            return None
        return {"hrvSummary": {"lastNightAvg": 50.04, "weeklyAvg": 52.0, "lastNight5MinHigh": 80.0, "status": "BALANCED", "feedbackPhrase": "HRV_BALANCED_1"}}

    def get_training_status(self, day):
        return {"mostRecentTrainingLoadBalance": {"metricsTrainingLoadBalanceDTOMap": {
            "d1": {"primaryTrainingDevice": True, "calendarDate": day, "trainingBalanceFeedbackPhrase": "AEROBIC_HIGH_SHORTAGE",
                   "monthlyLoadAerobicLow": 300.0, "monthlyLoadAerobicLowTargetMin": 200, "monthlyLoadAerobicLowTargetMax": 400,
                   "monthlyLoadAerobicHigh": 50.0, "monthlyLoadAerobicHighTargetMin": 150, "monthlyLoadAerobicHighTargetMax": 350,
                   "monthlyLoadAnaerobic": 500.0, "monthlyLoadAnaerobicTargetMin": 0, "monthlyLoadAnaerobicTargetMax": 100},
        }}}

    def get_activity_typed_splits(self, aid):
        return {"activityId": aid, "splits": [{"type": "INTERVAL_ACTIVE"}]}

    def query_garmin_graphql(self, query):
        assert "trainingPlanScalar" in query["query"]
        return {"data": {"trainingPlanScalar": {"trainingPlanWorkoutScheduleDTOS": [{
            "planName": "Media maratón",
            "workoutScheduleSummaries": [
                {"scheduleDate": "2026-10-10", "workoutId": 1, "workoutName": "Tempo", "workoutType": "running", "associatedActivityId": 77, "isRestDay": False},
                {"scheduleDate": "2026-10-11", "workoutName": "Descanso", "isRestDay": True},
            ]}]}}}

    # --- escrituras ---
    def schedule_workout(self, wid, d):
        if wid == 999:
            raise RuntimeError("boom")
        self.scheduled.append((wid, d))
        return {"ok": True}

    def unschedule_workout(self, sid):
        self.unscheduled.append(sid)
        return {}

    def delete_workout(self, wid):
        if wid == 404:
            raise RuntimeError("no existe")
        self.deleted.append(wid)


@pytest.fixture
def api(srv, monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(srv, "_get_api", lambda: fake)
    return fake


# ---------- escritura de actividad ----------
def test_set_perceived_effort_stores_times_ten(srv, api):
    out = _fn(srv.set_perceived_effort)("123", 7)
    assert out == {"ok": True, "activity_id": 123, "rpe": 7.0}
    _, url, kw = api.client.puts[0]
    assert url == "/activity-service/activity/123"
    assert kw["json"] == {"activityId": 123, "summaryDTO": {"directWorkoutRpe": 70}}
    assert kw["api"] is True


@pytest.mark.parametrize("bad", [-1, 10.5, 11])
def test_set_perceived_effort_rejects_out_of_range(srv, api, bad):
    with pytest.raises(ValueError):
        _fn(srv.set_perceived_effort)("123", bad)
    assert api.client.puts == []


def test_set_activity_feel_validates_values(srv, api):
    _fn(srv.set_activity_feel)("5", 75)
    assert api.client.puts[0][2]["json"]["summaryDTO"] == {"directWorkoutFeel": 75}
    with pytest.raises(ValueError):
        _fn(srv.set_activity_feel)("5", 60)


def test_set_name_and_description(srv, api):
    _fn(srv.set_activity_name)("9", "  Rodaje suave  ")
    assert api.client.puts[0][2]["json"] == {"activityId": 9, "activityName": "Rodaje suave"}
    with pytest.raises(ValueError):
        _fn(srv.set_activity_name)("9", "   ")
    _fn(srv.set_activity_description)("9", "")
    assert api.client.puts[-1][2]["json"] == {"activityId": 9, "description": ""}
    with pytest.raises(ValueError):
        _fn(srv.set_activity_name)("abc", "x")


def test_writes_can_be_disabled(srv, api, monkeypatch):
    monkeypatch.setattr(srv, "_PORTED_WRITES_DISABLED", True)
    for call in (
        lambda: _fn(srv.set_perceived_effort)("1", 5),
        lambda: _fn(srv.schedule_workouts)([{"workout_id": 1, "calendar_date": "2026-10-10"}]),
        lambda: _fn(srv.unschedule_workouts)([1]),
        lambda: _fn(srv.delete_workouts)([1]),
    ):
        with pytest.raises(RuntimeError, match="desactivadas"):
            call()
    assert api.client.puts == [] and api.scheduled == [] and api.deleted == []


# ---------- lecturas ----------
def test_heart_rate_zones_all_and_by_sport(srv, api):
    assert len(_fn(srv.get_heart_rate_zones)()["profiles"]) == 2
    assert _fn(srv.get_heart_rate_zones)("running")["profile"]["lactateThresholdHeartRateUsed"] == 164
    assert _fn(srv.get_heart_rate_zones)("generic")["profile"]["sport"] == "DEFAULT"
    with pytest.raises(RuntimeError):
        _fn(srv.get_heart_rate_zones)("swimming")


def test_weekly_intensity_minutes(srv, api):
    out = _fn(srv.get_weekly_intensity_minutes)("2026-10-09", 4)
    assert out["start_date"] == "2026-09-12" and out["end_date"] == "2026-10-09"
    assert out["weeks"][0]["total_minutes"] == 150  # 30 + 2*60
    assert out["weeks"][1]["total_minutes"] is None


def test_running_tolerance_trend_weekly(srv, api):
    out = _fn(srv.get_running_tolerance_trend)("2026-09-14", "2026-10-09")
    assert [p["date"] for p in out["trend"]] == ["2026-09-21", "2026-09-28"]  # ordenado
    assert out["trend"][1]["tolerance_km"] == 60.0
    assert out["trend"][1]["load_ratio"] == 1.12
    assert out["tolerance_change_km"] == 5.0
    with pytest.raises(ValueError):
        _fn(srv.get_running_tolerance_trend)("2026-01-01", "2026-10-09", "daily")  # >90 días
    with pytest.raises(ValueError):
        _fn(srv.get_running_tolerance_trend)("2026-09-14", "2026-10-09", "monthly")


def test_hrv_trend_skips_missing_days(srv, api):
    out = _fn(srv.get_hrv_trend)("2026-10-01", "2026-10-03")
    assert out["days_with_data"] == 2
    assert out["period_avg_ms"] == 50.0
    # el servidor traduce los estados de Garmin al español en la salida
    assert out["trend"][0]["status"] in ("BALANCED", "Equilibrado")
    with pytest.raises(ValueError):
        _fn(srv.get_hrv_trend)("2026-08-01", "2026-10-03")  # >30 días


def test_training_load_balance_status(srv, api):
    out = _fn(srv.get_training_load_balance)("2026-10-09")
    assert out["feedback"] == "AEROBIC_HIGH_SHORTAGE"
    assert out["aerobic_low"]["status"] == "within"
    assert out["aerobic_high"]["status"] == "below"
    assert out["anaerobic"]["status"] == "above"


def test_typed_splits_and_coach_workouts(srv, api):
    assert _fn(srv.get_activity_typed_splits)("42")["activity_id"] == 42
    out = _fn(srv.get_garmin_coach_workouts)("2026-10-09")
    assert out["training_plans"] == ["Media maratón"] and out["count"] == 2
    done, rest = out["workouts"]
    assert done["completed"] is True and done["activity_id"] == 77
    assert rest["is_rest_day"] is True and "workout_id" not in rest


# ---------- bloque ----------
def test_schedule_workouts_partial_failure_does_not_cancel_rest(srv, api):
    out = _fn(srv.schedule_workouts)([
        {"workout_id": 1, "calendar_date": "2026-10-10"},
        {"workout_id": 999, "calendar_date": "2026-10-11"},
        {"workout_id": 2, "calendar_date": "no-es-fecha"},
        {"workout_id": 3, "calendar_date": "2026-10-12"},
    ])
    assert out["scheduled"] == 2 and out["failed"] == 2
    assert api.scheduled == [(1, "2026-10-10"), (3, "2026-10-12")]
    with pytest.raises(ValueError):
        _fn(srv.schedule_workouts)([])


def test_unschedule_and_delete_workouts(srv, api):
    assert _fn(srv.unschedule_workouts)([10, 11])["removed"] == 2 and api.unscheduled == [10, 11]
    out = _fn(srv.delete_workouts)([1, 404, 2])
    assert out["deleted"] == 2 and out["failed"] == 1 and api.deleted == [1, 2]


def test_new_tools_registered_in_mcp(srv):
    import asyncio

    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    expected = {
        "set_perceived_effort", "set_activity_feel", "set_activity_name", "set_activity_description",
        "get_heart_rate_zones", "get_weekly_intensity_minutes", "get_running_tolerance_trend", "get_hrv_trend",
        "get_training_load_balance", "get_activity_typed_splits", "get_garmin_coach_workouts",
        "schedule_workouts", "unschedule_workouts", "delete_workouts",
    }
    assert expected <= names
