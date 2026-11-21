"""Prompts for a real chat model (Azure OpenAI / OpenAI-compatible). JSON output only."""
from __future__ import annotations

import json

from app.models import ESCALATE_MESSAGE, Draft
from app.tools import TOOL_DESCRIPTIONS

SYSTEM = (
    "You are FaultFinder, an assistant that helps maintenance technicians investigate faults on "
    "centrifugal pumps. You only use evidence returned by tools. You never invent page numbers, "
    "record IDs or measurements. Reply with a single JSON object and nothing else."
)

TASKS = {
    "triage": (
        "Classify the technician's report. Return JSON: "
        '{"in_scope": bool (true only if it is about an equipment fault or maintenance of a pump/motor), '
        '"machine_id": string|null (format CP-NN), "fault_code": string|null (format PF-NNN), '
        '"symptom_concepts": [short strings], "symptom_summary": string}'
    ),
    "next_action": (
        "Decide the next tool call to investigate the fault, or finish when you have enough evidence. "
        "Tools:\n" + "\n".join(TOOL_DESCRIPTIONS.values()) +
        '\nReturn JSON: {"tool": "<tool name>" or "finish", "args": {...}}. '
        "Prefer lookup_fault_code when a code is known, then find_similar_faults and search_manual."
    ),
    "draft": (
        "Write a draft recommendation from the observations only. Up to 3 ranked likely causes, checks to run, "
        "every claim with at least one citation. A citation is "
        '{"source": "manual"|"record", "ref": page number as string or record ID, "quote": exact text copied from that page or record}. '
        f'If the evidence is too thin, set status "escalate", leave causes empty and set escalation_message to "{ESCALATE_MESSAGE}". '
        "Return JSON matching this schema: " + json.dumps(Draft.model_json_schema())
    ),
}


def build_messages(task: str, payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM + "\n\n" + TASKS[task]},
        {"role": "user", "content": json.dumps(payload, default=str)[:60000]},
    ]
