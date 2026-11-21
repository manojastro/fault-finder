"""Writes a SYNTHETIC ~20 page stand-in manual for a centrifugal pump.

Used only when data/manual/ has no real manual. Page markers look like
"=== PAGE 7 ===". Section headings are numbered ("4.3 Suction piping").
"""
from __future__ import annotations

from pathlib import Path

from app.data_gen.catalog import FAULT_CODES

MANUAL_FILENAME = "SYNTHETIC_centrifugal_pump_manual.txt"
BANNER = "SYNTHETIC DOCUMENT - generated for a demo. Not a real manufacturer manual. Do not use for real equipment."

PROSE: dict[int, str] = {
    1: """FF-CP150 End-Suction Centrifugal Pump
Installation, Operation and Maintenance Manual (SYNTHETIC)

1 About this manual
This manual covers the FF-CP150 single-stage, end-suction centrifugal pump with a
close-coupled 15 kW electric motor. It is written for maintenance technicians and
operators. Read the safety chapter before any work on the pump.
Chapters: 2 Safety, 3 Description, 4 Installation, 5 Commissioning, 6 Operation,
7 Monitoring and fault codes, 8 Troubleshooting, 9 Maintenance, 10 Spare parts.""",
    2: """2 Safety information
2.1 General safety rules
Only trained and authorised persons may install, operate or maintain the pump.
Before any maintenance, isolate the motor electrically and apply lockout and tagout.
Never reach into the pump, the coupling or the shaft area while the pump is running.
The coupling guard must be fitted before the pump is started.
Electrical work on the motor and the control panel must be done by a qualified
electrician. If you notice smoke, sparking or a burning smell, stop the pump from a
safe position and inform a supervisor.""",
    3: """2.2 Pressure and hot fluid hazards
The pump casing and piping can contain fluid under pressure and at high temperature.
Close the suction and discharge valves and release pressure through the casing drain
before opening any joint. Never loosen flange bolts or the casing cover while the
system is pressurised. Wear the protective equipment listed in the site permit.
2.3 Lifting
Use the lifting points shown on the pump drawing. Never lift the pump by the motor
eye bolt when the pump end is attached.""",
    4: """3 Pump description
3.1 Main components
The pump consists of a volute casing, a closed impeller fixed to the shaft, a
cartridge mechanical seal, a bearing frame with two rolling bearings, a flexible
coupling and a three-phase induction motor. Wear rings between the impeller and the
casing limit internal recirculation. The bearing frame has grease nipples on the
drive-end and non-drive-end bearings.""",
    5: """3.2 Technical data
Rated flow: 150 m3/h at a head of 45 m.
Rated speed: 2950 rpm. Motor: 15 kW, 400 V, 3 phase, 50 Hz, rated current 28 A.
NPSH required at rated flow: 3.2 m.
Bearing housing temperature limit: 80 C. Vibration alarm limit: 4.5 mm/s RMS.
Maximum casing pressure: 16 bar. Maximum fluid temperature: 90 C.
Wear ring diametral clearance: new 0.35 mm, replace at 0.70 mm.""",
    6: """4 Installation
4.1 Foundation and baseplate
Mount the baseplate on a rigid concrete foundation. Grout the baseplate and tighten
the foundation bolts to the torque given on the installation drawing.
4.2 Shaft alignment
Align pump and motor shafts after grouting and again after the piping is connected.
Maximum parallel and angular misalignment: 0.05 mm measured with a dial indicator
or a laser alignment tool. Misalignment causes vibration, bearing heat and coupling
wear. Pipe strain must not move the pump; support the piping independently.""",
    7: """4.3 Suction piping and NPSH
Keep the suction line short, straight and one size larger than the pump suction.
Avoid air pockets; the line should rise steadily towards the pump. Fit a suction
strainer and keep it clean, because a fouled strainer reduces NPSH available and
causes cavitation. NPSH available must exceed NPSH required by at least 1 m.
Do not throttle the pump on the suction side.""",
    8: """5 Commissioning and start-up
5.1 Before the first start
Fill the casing and suction line with liquid and vent all air. Never run the pump
dry, even for a few seconds, because the mechanical seal faces will be damaged.
Check the direction of rotation against the arrow on the casing with the coupling
disconnected. Confirm the coupling guard is fitted.
5.2 Start-up
Open the suction valve fully. Start the pump with the discharge valve slightly open,
then open the discharge valve slowly to the duty point.""",
    9: """6 Operation
6.1 Operating window
Operate between 30 % and 110 % of the best efficiency point flow. Running far right
of the best efficiency point overloads the motor and raises NPSH required. Running
below minimum flow heats the fluid and increases vibration.
6.2 Shutdown
Close the discharge valve slowly, stop the motor, then close the suction valve if the
pump will stay idle.""",
    10: """7 Monitoring and fault codes
7.1 Controller and sensors
The pump controller reads bearing temperature, motor winding temperature, vibration
at the drive-end bearing housing, suction pressure, discharge pressure and motor
current. When a limit is exceeded the controller shows a fault code of the form
PF-1xx and records it in the event log. A fault code is a symptom, not a diagnosis:
use chapter 8 to investigate the cause.""",
    18: """9 Maintenance
9.1 Bearing lubrication
Re-grease the bearings every 2000 operating hours with 15 g of lithium complex grease
per bearing. Too much grease raises bearing temperature as much as too little grease.
Replace the bearings at 25000 hours or when vibration or noise shows bearing wear.""",
    19: """9.2 Mechanical seal replacement
Isolate, lock out and drain the pump before removing the seal. Replace the complete
cartridge seal; do not reuse seal faces. Set the seal at the setting length shown on
the seal drawing. Check the seal flush line is clear before restarting.
9.3 Impeller and wear ring inspection
Inspect the impeller every 8000 hours for erosion, cavitation pitting and deposits.
Measure wear ring clearance; replace the wear rings when clearance reaches 0.70 mm.""",
    20: """10 Spare parts
Recommended spares: one cartridge mechanical seal, one bearing set, one set of wear
rings, one set of coupling elastomer elements and one gasket set.
11 Glossary
BEP: best efficiency point. NPSH: net positive suction head. RMS: root mean square.
SYNTHETIC: this manual and all data in this repository are generated for a demo.""",
}


def _fault_table() -> str:
    rows = ["7.2 Fault code table", "Code | Name | Trigger condition | See page"]
    rows += [f"{fc.code} | {fc.name} | {fc.trigger} | {fc.page}" for fc in FAULT_CODES]
    return "\n".join(rows)


def _troubleshooting_entry(fc, number: int) -> str:
    lines = [f"8.{number} {fc.code} {fc.name}", f"Trigger condition: {fc.trigger}."]
    lines.append("Likely causes (most frequent first):")
    lines += [f"- {c.text}" for c in fc.causes]
    lines.append("Checks to run:")
    lines += [f"- {chk}" for chk in fc.checks]
    return "\n".join(lines)


def build_pages() -> dict[int, str]:
    pages = dict(PROSE)
    pages[11] = _fault_table()
    for i, fc in enumerate(FAULT_CODES, start=1):
        intro = "8 Troubleshooting\nIsolate and lock out the pump before any check that needs contact with moving parts.\n" if i == 1 else ""
        entry = intro + _troubleshooting_entry(fc, i)
        pages[fc.page] = (pages[fc.page] + "\n\n" + entry) if fc.page in pages else entry
    return dict(sorted(pages.items()))


def render() -> str:
    parts = []
    for n, text in build_pages().items():
        parts.append(f"=== PAGE {n} ===\n{BANNER}\n\n{text.strip()}\n")
    return "\n".join(parts)


def write_manual(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / MANUAL_FILENAME
    path.write_text(render(), encoding="utf-8")
    return path
