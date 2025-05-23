import yaml
from datetime import datetime

def parse_time(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value  # già datetime

def parse_incident_file(file_path: str) -> dict:
    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        if not data:
            raise ValueError("YAML vuoto o malformato.")
        # Parsing orari
        data['start_time'] = parse_time(data['start_time'])
        data['end_time'] = parse_time(data['end_time'])

        # Ordina timeline
        data['timeline'] = sorted(data.get('timeline', []))

        # Parsing logs
        if 'logs' in data:
            data['logs'] = [
                {
                    "timestamp": parse_time(line.split(' ')[0]),
                    "raw": line
                }
                for line in data['logs']
            ]

        # Parsing metriche
        if 'metrics' in data:
            for metric in data['metrics'].values():
                metric['values'] = [
                    {
                        "timestamp": parse_time(v['timestamp']),
                        "value": v['value']
                    }
                    for v in metric['values']
                ]

        return data

    except Exception as e:
        import traceback
        print("[ERROR] Parsing failed:")
        traceback.print_exc()
        return None
