# 🧠 AI Incident Helper

[![Streamlit](https://img.shields.io/badge/Streamlit-Cloud-red?logo=streamlit)](https://streamlit.io)
[![GPT](https://img.shields.io/badge/GPT-3.5--Turbo-blue?logo=openai)](https://platform.openai.com)
[![MIT License](https://img.shields.io/github/license/tuo-user/ai-incident-helper)](LICENSE)

Un'applicazione AI-driven per DevOps e SRE che semplifica l'analisi degli incidenti e genera automaticamente report post-mortem, oltre a offrire una dashboard multi-incidenti interattiva.

---

## 🚀 Funzionalità principali

- 📁 Upload di file YAML contenenti timeline, log, metriche, comunicazioni
- 🔍 Parsing automatico con calcolo di:
  - `MTTR` – Mean Time to Recovery
  - `TTD` – Time to Detect
  - `TTM` – Time to Mitigate
- 🧠 Generazione AI del report post-mortem tramite GPT-3.5
- 📈 Dashboard multi-incidenti con medie e grafici
- 💾 Download del report `.md` in un clic

---

## 🖼️ Interfaccia

### 🧠 Analisi Singolo Incidente
- Upload file `.yaml`
- Parsing dettagliato
- Generazione AI del report

### 📊 Dashboard Multi-Incidente
- Upload multiplo `.yaml`
- Tabella incidenti
- MTTR medio + grafico interattivo

---

## 📦 Installazione

```bash
git clone https://github.com/<tuo-user>/ai-incident-helper.git
cd ai-incident-helper
pip install -r requirements.txt
streamlit run streamlit_app.py
