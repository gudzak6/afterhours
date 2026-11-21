from datetime import UTC, date, datetime
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

from app.garmin.mapping import METERS_PER_MILE
from app.services.adherence import (
    assign_matches,
    build_weeks,
    compare_execution,
    parse_plan_csv,
    parse_plan_xlsx,
    sync_covers_date,
    workout_status,
)


def _plan(**kwargs):
    defaults = dict(
        id=1,
        scheduled_date=date(2026, 11, 8),
        workout_type="intervals",
        distance_meters=10000,
        repetitions=6,
        rep_distance_meters=1000,
        recovery_seconds=90,
        target_pace_seconds_per_mile=330,
        intensity=None,
        match_source=None,
        match_activity_id=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _activity(**kwargs):
    defaults = dict(
        id=10,
        garmin_activity_id=99,
        name="Intervals",
        start_time_local="2026-11-08 07:00:00",
        distance_meters=9000,
        average_speed_mps=METERS_PER_MILE / 335,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_repetition_comparison_uses_calculated_counts_and_pace():
    comparison = compare_execution(
        _plan(),
        _activity(),
        actual_type="intervals",
        repetition_count=5,
        repetition_pace=335,
        repetition_distance_meters=1000,
        recovery_seconds=90,
        recorded_effort=None,
    )
    assert comparison["execution"] == "partial"
    assert comparison["summary"] == "Completed 5 of 6 repetitions, averaging 5 seconds per mile slower than prescribed."


def test_past_plan_without_sync_is_not_missed():
    plan = _plan(workout_type="easy", repetitions=None, target_pace_seconds_per_mile=None)
    status = workout_status(plan, None, None, today=date(2026, 11, 11), covered=False, same_day_unmatched=False)
    assert status == "unmatched"
    assert sync_covers_date(scheduled=plan.scheduled_date, later_activity=False, last_sync_at=None) is False


def test_empty_day_after_a_later_activity_is_confirmed_missed():
    plan = _plan()
    assert sync_covers_date(scheduled=plan.scheduled_date, later_activity=True, last_sync_at=None) is True
    status = workout_status(plan, None, None, today=date(2026, 11, 11), covered=True, same_day_unmatched=False)
    assert status == "confirmed_missed"


def test_same_day_activity_that_does_not_match_stays_unmatched():
    status = workout_status(_plan(), None, None, today=date(2026, 11, 11), covered=True, same_day_unmatched=True)
    assert status == "unmatched"


def test_manual_match_is_kept_when_another_run_scores_higher():
    manual = _plan(match_source="manual", match_activity_id=10)
    other = _activity(id=11, distance_meters=10000)
    chosen = _activity()
    assigned = assign_matches([manual], [other, chosen], {11: "intervals", 10: "easy"})
    assert assigned[manual.id].id == 10


def test_one_activity_is_not_matched_to_two_plans():
    plans = [_plan(id=1), _plan(id=2, workout_type="easy", repetitions=None)]
    activity = _activity()
    assigned = assign_matches(plans, [activity], {10: "intervals"})
    assert list(assigned) == [1]


def test_weekly_variance_stays_blank_when_a_distance_is_not_prescribed():
    dated = date(2026, 11, 9)
    plans = [
        _plan(id=1, scheduled_date=dated, distance_meters=16093.44, workout_type="easy", repetitions=None),
        _plan(id=2, scheduled_date=dated, distance_meters=None, workout_type="strides", repetitions=8),
    ]
    activity = _activity(start_time_local="2026-11-09 07:00:00", distance_meters=16093.44)
    weeks = build_weeks(plans, [activity], {1: activity}, {1: "completed", 2: "scheduled"}, today=date(2026, 11, 11))
    assert weeks[0]["planned_miles_complete"] is False
    assert weeks[0]["variance_percent"] is None
    assert weeks[0]["in_progress"] is True
    assert weeks[0]["still_scheduled"] == 1


def test_csv_import_keeps_the_prescription_fields():
    text = "date,title,type,distance,reps,rep_distance,recovery_seconds,pace\n2026-11-12,Kilometer repeats,intervals,6,6,0.62,90,5:30\n"
    plans, errors = parse_plan_csv(text)
    assert errors == []
    assert plans[0]["workout_type"] == "intervals"
    assert plans[0]["repetitions"] == 6
    assert plans[0]["target_pace_seconds_per_mile"] == 330
    assert plans[0]["scheduled_date"] == date(2026, 11, 12)
    assert "pace: 5:30" in plans[0]["details"]
    assert "Kilometer repeats" not in plans[0]["details"]


def test_weekday_spreadsheet_keeps_each_cell():
    text = "Week of,Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday\n2026-11-16,Easy 6,\"8x400\n90s jog\",Off,Easy 5,,Long run 14,Easy 4\n"
    plans, errors = parse_plan_csv(text)
    assert errors == []
    by_day = {plan["scheduled_date"]: plan for plan in plans}
    assert by_day[date(2026, 11, 16)]["details"] == "Easy 6"
    tuesday = by_day[date(2026, 11, 17)]
    assert tuesday["title"] == "8x400"
    assert tuesday["details"] == "8x400\n90s jog"
    assert by_day[date(2026, 11, 18)]["workout_type"] == "recovery"
    assert date(2026, 11, 20) not in by_day
    assert by_day[date(2026, 11, 21)]["title"] == "Long run 14"


def test_week_number_spreadsheet_uses_the_start_date():
    text = "Week,Mon,Tue,Wed,Thu,Fri,Sat,Sun\n1,Easy 5,Rest,Easy 6,Off,Tempo 5,Easy 4,Long 12,Off\n2,Easy 6,Rest,Easy 6,Off,Tempo 6,Easy 4,Long 14,Off\n"
    missing, errors = parse_plan_csv(text)
    assert missing == []
    assert errors[0].startswith("This spreadsheet uses week numbers.")
    plans, placed_errors = parse_plan_csv(text, week_one=date(2026, 11, 18))
    assert placed_errors == []
    monday = next(plan for plan in plans if plan["title"] == "Easy 5")
    assert monday["scheduled_date"] == date(2026, 11, 16)
    second = next(plan for plan in plans if plan["title"] == "Long 14")
    assert second["scheduled_date"] == date(2026, 11, 29)


def test_spreadsheet_dates_follow_the_selected_start():
    import base64

    from app.config import Settings
    from app.services.program import workouts_from_program

    plans, _errors, source = workouts_from_program(
        Settings(),
        "plan.xlsx",
        None,
        base64.b64encode(_mileage_workbook()).decode(),
        today=date(2026, 11, 20),
        start=date(2026, 11, 25),
    )
    assert source == "spreadsheet"
    by_title = {plan["title"]: plan["scheduled_date"] for plan in plans}
    assert by_title["Drills/hill strides"] == date(2026, 11, 25)
    assert by_title["LT1/2"] == date(2026, 11, 27)
    assert by_title["Long Run"] == date(2026, 11, 30)
    assert "4x5'" in next(plan["details"] for plan in plans if plan["title"] == "LT1/2")


def test_mileage_and_workout_rows_keep_the_cell_note():
    plans, errors = parse_plan_xlsx(_mileage_workbook())
    assert errors == []
    by_day = {plan["scheduled_date"]: plan for plan in plans}
    assert set(by_day) == {date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 8)}
    monday = by_day[date(2026, 8, 3)]
    assert monday["title"] == "Drills/hill strides"
    assert monday["distance_meters"] == 5 * METERS_PER_MILE
    assert monday["workout_type"] == "strides"
    wednesday = by_day[date(2026, 8, 5)]
    assert wednesday["title"] == "LT1/2"
    assert wednesday["workout_type"] == "threshold"
    assert "4x5'" in wednesday["details"]
    assert wednesday["coach_notes"].startswith("Easy runs")
    assert by_day[date(2026, 8, 8)]["workout_type"] == "long_run"
    assert date(2026, 8, 4) not in by_day


def _mileage_workbook() -> bytes:
    sheet = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>Week</t></is></c>
      <c r="B2" t="inlineStr"><is><t>Monday</t></is></c>
      <c r="C2" t="inlineStr"><is><t>Tuesday</t></is></c>
      <c r="D2" t="inlineStr"><is><t>Wednesday</t></is></c>
      <c r="E2" t="inlineStr"><is><t>Thursday</t></is></c>
      <c r="F2" t="inlineStr"><is><t>Friday</t></is></c>
      <c r="G2" t="inlineStr"><is><t>Saturday</t></is></c>
      <c r="H2" t="inlineStr"><is><t>Sunday</t></is></c>
      <c r="J2" t="inlineStr"><is><t>General Notes</t></is></c>
    </row>
    <row r="3">
      <c r="A3"><v>46237</v></c>
      <c r="B3"><v>5</v></c>
      <c r="C3"><v>0</v></c>
      <c r="D3"><v>8</v></c>
      <c r="G3"><v>12</v></c>
      <c r="J3" t="inlineStr"><is><t>Easy runs this week</t></is></c>
    </row>
    <row r="4">
      <c r="A4" t="inlineStr"><is><t>Workout</t></is></c>
      <c r="B4" t="inlineStr"><is><t>Drills/hill strides</t></is></c>
      <c r="D4" t="inlineStr"><is><t>LT1/2</t></is></c>
      <c r="G4" t="inlineStr"><is><t>Long Run</t></is></c>
    </row>
    <row r="16">
      <c r="A16" t="inlineStr"><is><t>Supplementals</t></is></c>
      <c r="B16" t="inlineStr"><is><t>6x100m strides</t></is></c>
    </row>
  </sheetData>
</worksheet>"""
    comments = """<?xml version="1.0" encoding="UTF-8"?>
<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <commentList><comment ref="D3"><text><t>4x5' @ LT1/LT2</t></text></comment></commentList>
</comments>"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="August" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    sheet_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="../comments1.xml"/>
</Relationships>"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr("xl/worksheets/_rels/sheet1.xml.rels", sheet_rels)
        archive.writestr("xl/comments1.xml", comments)
    return buffer.getvalue()


def test_future_workout_stays_scheduled():
    status = workout_status(_plan(scheduled_date=date(2026, 11, 12)), None, None, today=date(2026, 11, 11), covered=True, same_day_unmatched=False)
    assert status == "scheduled"
