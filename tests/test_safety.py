import pytest

from app.agent.runner import Agent
from app.safety.check import check_report

CRITICAL = [
    ("I got an electric shock from the starter panel", "electric_shock"),
    ("Felt a tingling when I touched the CP-02 motor", "electric_shock"),
    ("Exposed wire hanging out of the junction box", "electric_shock"),
    ("Sparking at the motor terminals", "electric_shock"),
    ("Water inside the terminal box of the motor", "electric_shock"),
    ("Smoke coming out of the motor fan cover", "smoke_or_fire"),
    ("There is a burning smell near the pump", "smoke_or_fire"),
    ("Smells of burning rubber at the coupling", "smoke_or_fire"),
    ("Discharge hose burst, fluid everywhere", "pressure_release"),
    ("Hot water spraying from the casing joint", "pressure_release"),
    ("Relief valve lifting repeatedly on the discharge", "pressure_release"),
    ("Going to open the drain while still pressurised", "pressure_release"),
    ("Coupling guard is off and the pump is running", "guard_removed"),
    ("We removed the guard to watch the coupling run", "guard_removed"),
    ("Can I reach in and clear the strainer while it is running?", "guard_removed"),
    ("Sleeve got caught on the shaft", "guard_removed"),
    ("Bypassed the interlock to restart the pump", "lockout_bypass"),
    ("Working on the seal without lockout", "lockout_bypass"),
    ("Operator injured by the coupling", "injury_or_hazardous_substance"),
    ("Chemical leak from the dosing line next to CP-04", "injury_or_hazardous_substance"),
]

NOT_CRITICAL = [
    "CP-03 bearing housing too hot to touch, 91 C, PF-102",
    "CP-09 PF-105 discharge pressure 3.1 bar against 4.4 bar expected",
    "CP-01 high vibration 8 mm/s, coupling guard is fitted",
    "Seal dripping about 20 drops per minute",
    "Motor thermistor trip, fan cover dusty",
    "Pressure reading jumping around on the display",
]


@pytest.mark.parametrize("text,rule", CRITICAL)
def test_safety_critical_reports_match(settings, text, rule):
    res = check_report(text, settings.safety_rules_path)
    assert res.is_safety_critical, text
    assert rule in res.matched_rules
    assert res.message.startswith("STOP WORK") and "qualified supervisor" in res.message


@pytest.mark.parametrize("text", NOT_CRITICAL)
def test_normal_reports_do_not_match(settings, text):
    assert not check_report(text, settings.safety_rules_path).is_safety_critical


def test_rules_file_is_marked_provisional(settings):
    res = check_report("anything", settings.safety_rules_path)
    assert "PROVISIONAL" in res.rules_status


class ExplodingLLM:
    model = "must-not-be-called"

    def complete_json(self, task, payload):
        raise AssertionError("the model must not be called for a safety-critical report")


def test_safety_stop_happens_before_any_model_call(settings, store):
    agent = Agent(settings, store, llm=ExplodingLLM(), trace_dir=None)
    res = agent.investigate("Smoke from CP-04 motor and it smells burnt")
    assert res["status"] == "safety_stop"
    assert res["draft"] is None and res["tool_calls"] == []
    assert res["totals"]["llm_calls"] == 0
