"""SYNTHETIC fault catalog for a generic end-suction centrifugal pump.

This is the single source used to write the SYNTHETIC stand-in manual and the
SYNTHETIC fault history, so both agree. It was drafted by the build agent and is
NOT engineering guidance: a qualified mechanical engineer must review it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cause:
    text: str  # wording as printed in the manual
    category: str  # canonical label used by data, agent and evals
    weight: float  # relative frequency in the synthetic history
    fix: str  # typical corrective action recorded in the history


@dataclass(frozen=True)
class FaultCode:
    code: str
    name: str
    trigger: str
    page: int  # page of the troubleshooting entry in the synthetic manual
    causes: tuple[Cause, ...]
    checks: tuple[str, ...]
    symptoms: tuple[str, ...] = field(default=())  # phrases technicians use


FAULT_CODES: tuple[FaultCode, ...] = (
    FaultCode(
        "PF-101", "High vibration", "Overall vibration at a bearing housing above 4.5 mm/s RMS for 60 s", 12,
        (
            Cause("Shaft misalignment between pump and motor", "misalignment", 0.40,
                  "Re-aligned pump and motor shafts to within 0.05 mm"),
            Cause("Impeller imbalance from deposits or damage", "impeller_imbalance", 0.25,
                  "Cleaned impeller deposits and re-balanced impeller"),
            Cause("Worn or damaged rolling bearings", "bearing_wear", 0.20, "Replaced pump bearings"),
            Cause("Loose foundation or baseplate bolts", "loose_foundation", 0.15,
                  "Re-torqued baseplate and foundation bolts"),
        ),
        (
            "Measure vibration velocity at both bearing housings in horizontal, vertical and axial directions",
            "Check shaft alignment with a dial indicator or laser alignment tool",
            "Inspect the impeller for deposits, erosion or missing material",
            "Check torque on foundation and baseplate bolts",
        ),
        ("vibrating a lot", "shaking badly", "high vibration on the bearing housing", "excessive vibration"),
    ),
    FaultCode(
        "PF-102", "Bearing over-temperature", "Bearing housing temperature above 80 C", 12,
        (
            Cause("Worn or damaged rolling bearings", "bearing_wear", 0.35, "Replaced pump bearings"),
            Cause("Over-lubrication of the bearings", "over_lubrication", 0.25,
                  "Purged excess grease and reset lubrication schedule"),
            Cause("Insufficient or degraded lubricant", "under_lubrication", 0.25,
                  "Re-greased bearings with the specified grease"),
            Cause("Shaft misalignment between pump and motor", "misalignment", 0.15,
                  "Re-aligned pump and motor shafts to within 0.05 mm"),
        ),
        (
            "Measure bearing housing temperature with a contact thermometer",
            "Check grease quantity and condition against the lubrication schedule",
            "Listen to the bearings with a stethoscope for roughness",
            "Check shaft alignment with a dial indicator or laser alignment tool",
        ),
        ("bearing running hot", "bearing housing too hot to touch", "bearing temperature high", "overheating bearing"),
    ),
    FaultCode(
        "PF-103", "Mechanical seal leakage", "Seal leak detector wet or visible leakage above 10 drops per minute", 13,
        (
            Cause("Worn mechanical seal faces", "seal_wear", 0.50, "Replaced mechanical seal"),
            Cause("Seal damaged by dry running", "dry_running", 0.25,
                  "Replaced mechanical seal and corrected priming procedure"),
            Cause("Incorrect seal installation or setting length", "seal_installation_error", 0.25,
                  "Re-installed mechanical seal at the correct setting length"),
        ),
        (
            "Inspect the seal area and measure the leakage rate",
            "Check the seal flush line for flow and blockage",
            "Check the seal setting length against the seal drawing",
            "Review recent start-up records for dry running",
        ),
        ("leaking at the seal", "dripping from the shaft seal", "water leaking near the shaft", "seal leak"),
    ),
    FaultCode(
        "PF-104", "Cavitation detected", "Suction pressure below the NPSH alarm limit with high-frequency noise", 13,
        (
            Cause("Insufficient NPSH available at the suction", "low_npsh", 0.40,
                  "Raised suction tank level and reduced suction losses"),
            Cause("Blocked or fouled suction strainer", "blocked_suction_strainer", 0.35,
                  "Cleaned suction strainer"),
            Cause("Suction valve partly closed", "suction_valve_restricted", 0.15, "Fully opened suction valve"),
            Cause("Fluid temperature higher than design", "high_fluid_temperature", 0.10,
                  "Restored process cooling to design temperature"),
        ),
        (
            "Measure suction pressure and compare with the NPSH required",
            "Inspect and clean the suction strainer",
            "Confirm the suction valve is fully open",
            "Measure fluid temperature at the suction",
        ),
        ("noise like gravel in the pump", "crackling sound from the casing", "cavitation noise", "sounds like pumping marbles"),
    ),
    FaultCode(
        "PF-105", "Low discharge pressure", "Discharge pressure more than 15 % below the duty point", 14,
        (
            Cause("Worn impeller or wear rings", "impeller_wear", 0.40, "Replaced impeller and wear rings"),
            Cause("Air entering the suction line", "air_entrainment", 0.25,
                  "Sealed suction flange leak and vented casing"),
            Cause("Blocked or fouled suction strainer", "blocked_suction_strainer", 0.25,
                  "Cleaned suction strainer"),
            Cause("Wrong direction of rotation", "wrong_rotation", 0.10,
                  "Swapped two motor phases to correct rotation"),
        ),
        (
            "Measure discharge pressure and compare with the pump curve",
            "Measure wear ring clearance during the next inspection",
            "Check the suction line and flanges for air leaks",
            "Confirm direction of rotation against the arrow on the casing",
        ),
        ("pressure is low on the discharge", "not making pressure", "flow has dropped", "weak output"),
    ),
    FaultCode(
        "PF-106", "Motor overload", "Motor current above 110 % of rated current for 30 s", 14,
        (
            Cause("Operating far right of the best efficiency point", "excess_flow", 0.35,
                  "Throttled discharge valve back to the duty point"),
            Cause("Fluid viscosity or density above design", "high_viscosity", 0.20,
                  "Restored fluid to specification"),
            Cause("Mechanical binding or rubbing in the pump", "mechanical_binding", 0.25,
                  "Freed rubbing impeller and replaced damaged wear ring"),
            Cause("Supply voltage imbalance between phases", "voltage_imbalance", 0.20,
                  "Electrician corrected supply voltage imbalance"),
        ),
        (
            "Measure motor current on all three phases",
            "Check the discharge valve position and actual flow",
            "Rotate the shaft by hand after lockout to feel for binding",
            "Ask an electrician to measure supply voltage on all phases",
        ),
        ("motor tripping on overload", "drawing high amps", "high current on the motor", "overload relay keeps tripping"),
    ),
    FaultCode(
        "PF-107", "Dry run / loss of prime", "Motor power below 40 % of rated with no discharge flow", 15,
        (
            Cause("Pump running dry with no liquid in the casing", "dry_running", 0.35,
                  "Re-primed pump and added low-level interlock check"),
            Cause("Air entering the suction line", "air_entrainment", 0.25,
                  "Sealed suction flange leak and vented casing"),
            Cause("Supply tank level too low", "empty_supply_tank", 0.25, "Restored supply tank level"),
            Cause("Leaking foot valve on the suction line", "foot_valve_leak", 0.15, "Replaced foot valve"),
        ),
        (
            "Check the supply tank level",
            "Vent the casing and confirm the pump is primed",
            "Check the suction line and flanges for air leaks",
            "Inspect the foot valve for leakage",
        ),
        ("lost prime", "no flow at all", "running but nothing coming out", "pump running dry"),
    ),
    FaultCode(
        "PF-108", "High discharge pressure", "Discharge pressure above 120 % of the duty point", 15,
        (
            Cause("Discharge valve closed or nearly closed", "discharge_valve_closed", 0.55,
                  "Opened discharge valve to the duty position"),
            Cause("Blocked discharge line or check valve", "blocked_discharge_line", 0.45,
                  "Cleared blockage in discharge line"),
        ),
        (
            "Confirm the discharge valve position",
            "Check the discharge check valve and line for blockage",
            "Compare discharge pressure with the pump curve at zero flow",
        ),
        ("discharge pressure too high", "pressure gauge reading very high", "deadheading", "high pressure alarm on discharge"),
    ),
    FaultCode(
        "PF-109", "Motor winding over-temperature", "Motor winding thermistor above trip temperature", 16,
        (
            Cause("Blocked motor cooling fan or fins", "blocked_cooling_fan", 0.40, "Cleaned motor fan cover and cooling fins"),
            Cause("Operating far right of the best efficiency point", "excess_flow", 0.30,
                  "Throttled discharge valve back to the duty point"),
            Cause("Supply voltage imbalance between phases", "voltage_imbalance", 0.30,
                  "Electrician corrected supply voltage imbalance"),
        ),
        (
            "Inspect the motor fan cover and cooling fins for dirt",
            "Measure motor current on all three phases",
            "Ask an electrician to measure supply voltage on all phases",
        ),
        ("motor running hot", "motor thermistor trip", "motor overheating", "motor casing very hot"),
    ),
    FaultCode(
        "PF-110", "Coupling noise or wear", "Coupling inspection finding or rhythmic knocking at the coupling", 16,
        (
            Cause("Worn flexible coupling elements", "worn_coupling", 0.55, "Replaced coupling elastomer elements"),
            Cause("Shaft misalignment between pump and motor", "misalignment", 0.45,
                  "Re-aligned pump and motor shafts to within 0.05 mm"),
        ),
        (
            "Inspect the coupling elements for wear after lockout",
            "Check shaft alignment with a dial indicator or laser alignment tool",
        ),
        ("knocking at the coupling", "coupling rubber worn", "clunking from the coupling", "coupling noise"),
    ),
    FaultCode(
        "PF-111", "Pressure sensor fault", "Pressure transmitter signal outside 4 to 20 mA", 17,
        (
            Cause("Failed pressure transmitter", "sensor_failure", 0.55, "Replaced pressure transmitter"),
            Cause("Damaged or loose sensor wiring", "wiring_fault", 0.45, "Repaired sensor cable and terminal"),
        ),
        (
            "Compare the transmitter reading with a local pressure gauge",
            "Check the transmitter loop current with a calibrated meter",
            "Inspect the sensor cable and terminals for damage",
        ),
        ("pressure reading jumping around", "pressure signal lost", "sensor fault on the screen", "gauge and display disagree"),
    ),
    FaultCode(
        "PF-112", "Abnormal noise", "Operator report of knocking, grinding or rattling", 17,
        (
            Cause("Worn or damaged rolling bearings", "bearing_wear", 0.45, "Replaced pump bearings"),
            Cause("Foreign object in the impeller", "foreign_object", 0.30, "Removed foreign object from impeller"),
            Cause("Insufficient NPSH available at the suction", "low_npsh", 0.25,
                  "Raised suction tank level and reduced suction losses"),
        ),
        (
            "Listen to the bearings with a stethoscope for roughness",
            "Inspect the impeller eye for foreign objects after lockout",
            "Measure suction pressure and compare with the NPSH required",
        ),
        ("grinding noise", "rattling sound", "strange knocking inside the pump", "loud noise from the pump end"),
    ),
)

BY_CODE = {fc.code: fc for fc in FAULT_CODES}
CATEGORIES = sorted({c.category for fc in FAULT_CODES for c in fc.causes})
