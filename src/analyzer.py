from datetime import datetime, timedelta

def calculate_mttr(incident: dict) -> timedelta:
    return incident["end_time"] - incident["start_time"]

def calculate_ttd(incident: dict) -> timedelta:
    # Trova primo evento/alert
    for event in incident.get("timeline", []):
        if "Alert" in event or "alert" in event:
            event_time = extract_time_from_event(event, incident["start_time"])
            return event_time - incident["start_time"]
    return timedelta(0)

def calculate_ttm(incident: dict) -> timedelta:
    for event in incident.get("timeline", []):
        if "Fix" in event or "Rollback" in event or "Recovered" in event or "Mitigated" in event:
            event_time = extract_time_from_event(event, incident["start_time"])
            return event_time - incident["start_time"]
    return timedelta(0)

def extract_time_from_event(event: str, base_time: datetime) -> datetime:
    try:
        time_part = event.strip().split(" ")[0]
        event_time = datetime.strptime(time_part, "%H:%M")
        return base_time.replace(hour=event_time.hour, minute=event_time.minute)
    except Exception:
        return base_time

