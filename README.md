# 🧠 AI Incident Helper v2

Dall'incidente al post-mortem *blameless*: timeline classificata, metriche (TTD, TTA, TTM, TTR, MTTR) e analisi scritta da un modello, con causa principale, evidenze e azioni prioritizzate. Funziona con Anthropic, OpenAI o un **modello sul tuo hardware**, e anche **offline** senza IA.

## Cosa fa

1. **Da note grezze a YAML.** Incolli export di Slack/Teams, appunti, righe di log; l'IA prepara il file dell'incidente con timeline, servizi, log e messaggi. Lo controlli e lo correggi prima di andare avanti.
2. **Classifica la timeline.** Ogni evento riceve una fase: impatto, rilevamento, indagine, azione di mitigazione, mitigato, risolto, comunicazione. Con l'IA il modello legge anche log e chat; senza, usa regole a parole chiave. Le fasi scritte a mano nel YAML non vengono mai toccate.
3. **Calcola le metriche in codice.** Non le fa calcolare al modello.
4. **Scrive il post-mortem** con struttura fissa: sintesi, impatto, causa principale con livello di affidabilità (*confermata / probabile / ipotesi*) ed evidenze citate, fattori, cosa ha funzionato e cosa no, azioni P1–P3 con tipo e team, domande aperte.
5. **Dashboard** su più incidenti: medie e mediane, MTTR, export CSV.

## Metriche

Tutte misurate dall'inizio dell'impatto (`start_time`):

| | | evento |
|---|---|---|
| **TTD** | time to detect | primo evento `detection` |
| **TTA** | time to act | prima `mitigation_action` |
| **TTM** | time to mitigate | primo `mitigated`, altrimenti `resolved` |
| **TTR** | time to resolve | `end_time` |
| **MTTR** | media dei TTR | su più incidenti |

Se la timeline non contiene un evento, la metrica è *n/d*. Non diventa 0 come nella v1.

## Avvio

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # metti la chiave
streamlit run streamlit_app.py
```

Da riga di comando:

```bash
python -m incident_helper analyze data/example_db_crash.yaml --out pm.md
python -m incident_helper analyze data/example_db_crash.yaml --no-ai      # offline
python -m incident_helper extract data/raw/example_teams_export.txt --date 2026-11-03 --out inc.yaml
python -m incident_helper stats data/                                      # MTTR & co.
python -m incident_helper doctor                                           # configurazione risolta
```

## Configurazione IA

| Variabile | |
|---|---|
| `AI_PROVIDER` | `anthropic` (default) · `openai` · `local` |
| `AI_MODEL` | obbligatorio per `openai` e `local` |
| `AI_BASE_URL` | server compatibile OpenAI per `local` (llama.cpp, vLLM, Ollama, LM Studio) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | chiavi dei fornitori |
| `AI_LANGUAGE` | lingua del report, default `Italian` |
| `INCIDENT_REDACT` | `1` / `0` per forzare l'oscuramento |

### Dati sensibili

Log e chat di un incidente contengono spesso indirizzi IP, email, token e password. Con un fornitore esterno (`anthropic`, `openai`) il testo viene **oscurato prima dell'invio**: chiavi AWS, token GitHub, JWT, `password=...`, email e IP diventano segnaposto. È una rete di sicurezza, non una garanzia.

Per materiale che non può uscire dalla tua rete usa `AI_PROVIDER=local` con un modello sul tuo server:

```bash
export AI_PROVIDER=local AI_MODEL=bonsai-2-27b AI_BASE_URL=http://nero.lan:8080/v1
```

## Formato del file incidente

```yaml
incident_id: INC-2025-04-22
title: Crash del primario PostgreSQL     # opzionale
severity: SEV2                           # opzionale
services: [api, postgres]                # opzionale
start_time: 2025-04-22T18:10:00Z         # inizio impatto
end_time: 2025-04-22T19:05:00Z           # servizio ripristinato

timeline:
  - "18:10 DB connections timeout in prod-eu"           # HH:MM sul giorno di start_time
  - "2025-04-22T18:12:00Z Alert fired"                   # oppure timestamp completo
  - {time: "18:35", text: "Failover completed", phase: mitigated}   # fase fissata a mano

logs:
  - "2025-04-22T18:20:17Z dba NOTE: primary crashed, WAL logs incomplete"

metrics:
  db_connection_errors:
    unit: count
    values:
      - { timestamp: 2025-04-22T18:10:00Z, value: 78 }

team_comms:
  platform: slack
  messages:
    - { time: "18:16", user: "DBA", message: "Investigating primary DB crash" }
```

Gli orari `HH:MM` che tornano indietro di più di 6 ore sono considerati dopo la mezzanotte. Esempi in [`data/`](data/); un export grezzo da provare con *extract* in [`data/raw/`](data/raw/).

## Cosa è cambiato rispetto al 2025

- Nel commit `712f25f` (maggio 2025) parser, generatore, app e file di esempio erano stati sostituiti per errore da segnaposto (`pass`, `...`). Da allora l'app non funzionava. Gli esempi sono stati recuperati dalla storia git.
- `gpt-4` scritto nel codice, spento da OpenAI il 23 ottobre 2026 → fornitore e modello da variabili d'ambiente, più l'opzione locale.
- Prompt in prosa con `temperature=0.7` → output strutturato con schema; i numeri li calcola il codice.
- "Root cause (guess if not explicitly given)" → causa con livello di affidabilità ed evidenze; quello che i dati non dicono va nelle domande aperte.
- Fasi della timeline per parole chiave → classificazione IA (euristiche come ripiego).
- MTTR di un singolo incidente → TTR per incidente, MTTR come media.
- Tre app Streamlit duplicate → una sola, con tre viste.
- Nuovi: estrazione da note grezze, oscuramento, CLI, 32 test offline, CI.

## Sviluppo

```bash
pip install -e ".[dev,ai,app]"
pytest -q          # nessuna chiamata di rete
ruff check . && ruff format --check .
```

```
incident_helper/
  parser.py      YAML → Incident (e ritorno)
  phases.py      fasi della timeline (euristiche / IA) e metriche
  postmortem.py  analisi strutturata + rendering Markdown
  extract.py     note grezze → Incident
  redact.py      oscuramento di segreti e dati personali
  ai.py, llm.py  client multi-fornitore (llm.py è lo stesso di ai-devops-starter-kit)
  pipeline.py    operazioni usate da CLI e app
streamlit_app.py
```

MIT © Massimo Danieli
