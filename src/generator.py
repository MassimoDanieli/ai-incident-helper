from openai import OpenAI
import os
from datetime import timedelta
from typing import Dict

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def build_prompt(incident: Dict, mttr: timedelta, ttd: timedelta, ttm: timedelta) -> str:
    return f"""
You are an SRE expert helping a team write an incident post-mortem report.

Incident ID: {incident["incident_id"]}
Start Time: {incident["start_time"].isoformat()}
End Time: {incident["end_time"].isoformat()}
MTTR: {mttr}
Time to Detect (TTD): {ttd}
Time to Mitigate (TTM): {ttm}

Timeline of events:
{chr(10).join(["- " + e for e in incident["timeline"]])}

Relevant logs:
{chr(10).join(["- " + l["raw"] for l in incident.get("logs", [])[:5]])}

Team communications (Slack):
{chr(10).join(["- " + m["time"] + " " + m["user"] + ": " + m["message"]
               for m in incident.get("team_comms", {}).get("messages", [])[:5]])}

Write a Markdown-formatted post-mortem draft including:
- Executive Summary
- Timeline
- Impact
- Root Cause (guess if not explicitly given)
- Lessons Learned
- Action Items
"""

def generate_postmortem(incident: Dict, mttr, ttd, ttm) -> str:
    prompt = build_prompt(incident, mttr, ttd, ttm)

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a Site Reliability Engineer assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=1024
    )

    return response.choices[0].message.content

