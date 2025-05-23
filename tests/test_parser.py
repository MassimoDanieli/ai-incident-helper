import os
import pytest
from datetime import datetime
from src.parser import parse_incident_file

@pytest.fixture
def incident_file():
    return os.path.join("data", "example_incident.yaml")

def test_parse_incident_file(incident_file):
    data = parse_incident_file(incident_file)

    assert data['incident_id'] == "INC-2025-04-01"
    assert isinstance(data['start_time'], datetime)
    assert isinstance(data['end_time'], datetime)
    assert len(data['timeline']) > 0

    assert 'logs' in data
    assert isinstance(data['logs'][0]['timestamp'], datetime)

    assert 'metrics' in data
    assert 'latency_p95' in data['metrics']
    assert isinstance(data['metrics']['latency_p95']['values'][0]['timestamp'], datetime)

    assert 'team_comms' in data
    assert data['team_comms']['platform'] == 'slack'
    assert isinstance(data['team_comms']['messages'], list)

