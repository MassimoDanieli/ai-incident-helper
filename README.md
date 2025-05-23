# 🧠 AI Incident Helper

Un'applicazione AI-powered per Site Reliability Engineers (SRE), che supporta l'analisi degli incidenti e la generazione automatica di report post-mortem.

---

## 🚀 Funzionalità principali

- 📁 Caricamento di uno o più file `.yaml` di incidenti
- 🔍 Parsing automatico della timeline, log, metriche e comunicazioni
- 📊 Calcolo automatico di metriche SRE:
  - MTTR (Mean Time to Recovery)
  - TTD (Time to Detect)
  - TTM (Time to Mitigate)
- 🧠 Generazione automatica del report post-mortem con LLM (GPT-4 o GPT-3.5)
- 📈 Dashboard aggregata con grafici interattivi
- 💾 Download del report generato in formato `.md`

---

## 🧪 Esempio YAML valido

```yaml
incident_id: INC-2025-04-02
start_time: 2025-04-02T10:12:00Z
end_time: 2025-04-02T11:00:00Z

timeline:
  - "10:12 API latency > 5s in us-east"
  - "10:15 Alert fired: 'High latency'"
  - "10:17 Slack: Alice - Looks like DB lagging"
  - "10:25 Fix deployed by deploy-bot"
  - "11:00 System stabilized"

logs:
  - "2025-04-02T10:11:50Z api-gateway TimeoutError: Request timed out"
  - "2025-04-02T10:14:20Z alertmanager Alert triggered: latency > 5s"
  - "2025-04-02T10:24:50Z deploy-bot INFO: hotfix applied"

metrics:
  latency_p95:
    unit: ms
    values:
      - { timestamp: 2025-04-02T10:10:00Z, value: 3800 }
      - { timestamp: 2025-04-02T10:15:00Z, value: 7600 }
      - { timestamp: 2025-04-02T10:30:00Z, value: 3300 }
      - { timestamp: 2025-04-02T11:00:00Z, value: 1500 }

team_comms:
  platform: slack
  messages:
    - { time: "10:17", user: "Alice", message: "Looks like DB lagging" }
    - { time: "10:18", user: "Bob", message: "Checking RDS metrics" }

