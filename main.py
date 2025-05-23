from src.parser import parse_incident_file
from src.analyzer import calculate_mttr, calculate_ttd, calculate_ttm
from src.generator import generate_postmortem

if __name__ == "__main__":
    incident = parse_incident_file("data/example_incident.yaml")

    mttr = calculate_mttr(incident)
    ttd = calculate_ttd(incident)
    ttm = calculate_ttm(incident)

    print(f"\n✅ Generating post-mortem...\n")
    report = generate_postmortem(incident, mttr, ttd, ttm)
    print(report)

