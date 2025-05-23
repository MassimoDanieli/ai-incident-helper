from datetime import datetime, timedelta
from typing import Dict

def calculate_mttr(incident: Dict) -> timedelta:
    return incident["end_time"] - incident["start_time"]

def extract_time_from_event(event: str, base_time: datetime) -> datetime:
    parts = event.split(" ", 1)
    try:
        hour, minute = map(int, parts[0].split(":"))
        return base_time.replace(hour=hour, minute=minute)
    except (ValueError, IndexError):
        return base_time

def calculate_ttd(incident: Dict) -> timedelta:
    for event in incident["timeline"]:
        if "alert" in event.lower():
            event_time = extract_time_from_event(event, incident["start_time"])
            return event_time - incident["start_time"]
    return timedelta(0)

def calculate_ttm(incident: Dict) -> timedelta:
    for event in incident["timeline"]:
        if any(k in event.lower() for k in ["rollback", "mitigation", "fix deployed"]):
            event_time = extract_time_from_event(event, incident["start_time"])
            return event_time - incident["start_time"]
    return timedelta(0)

