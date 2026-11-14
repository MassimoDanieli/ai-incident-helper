"""AI Incident Helper — Streamlit UI.

Run:  streamlit run streamlit_app.py
AI backend from env vars (see README): AI_PROVIDER, AI_MODEL, AI_BASE_URL...
On Streamlit Cloud put them in the app secrets; they are exported to env below.
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st

from incident_helper import extract, parser, pipeline
from incident_helper.ai import make_client
from incident_helper.llm import AIConfigError

st.set_page_config(page_title="AI Incident Helper", page_icon="🧠", layout="wide")

# Streamlit Cloud: secrets -> environment
try:
    for key, value in st.secrets.items():
        if isinstance(value, str):
            os.environ.setdefault(key, value)
except Exception:  # no secrets file locally
    pass


@st.cache_resource
def get_client(redact: bool):
    return make_client(redact)


def client_or_none(use_ai: bool, redact: bool):
    if not use_ai:
        return None
    try:
        return get_client(redact)
    except AIConfigError as exc:
        st.error(f"Configurazione IA mancante: {exc}")
        st.stop()


with st.sidebar:
    st.title("🧠 AI Incident Helper")
    view = st.radio("Vista", ["Post-mortem", "Da note grezze", "Dashboard"], label_visibility="collapsed")
    st.divider()
    use_ai = st.toggle("Usa l'IA", value=bool(os.environ.get("AI_PROVIDER") or os.environ.get("ANTHROPIC_API_KEY")))
    provider = os.environ.get("AI_PROVIDER", "anthropic")
    redact = st.toggle(
        "Oscura dati sensibili prima dell'invio",
        value=provider in {"anthropic", "openai"},
        help="Email, IP, token, chiavi e password vengono sostituiti prima di mandare il testo al modello.",
    )
    language = st.selectbox("Lingua del report", ["Italian", "English"])
    if use_ai:
        st.caption(f"Backend: `{provider}` · `{os.environ.get('AI_MODEL', 'default')}`")
    else:
        st.caption("Modalità offline: metriche ed euristiche, nessuna chiamata a modelli.")


def show_analysis(result: pipeline.Analysis) -> None:
    m = result.metrics.minutes()
    cols = st.columns(4)
    for col, (label, key, help_text) in zip(
        cols,
        [
            ("TTD", "ttd", "Time to detect: inizio impatto → primo allarme"),
            ("TTA", "tta", "Time to act: inizio → prima azione di mitigazione"),
            ("TTM", "ttm", "Time to mitigate: inizio → impatto ridotto"),
            ("TTR", "ttr", "Time to resolve: inizio → fine"),
        ],
        strict=True,
    ):
        col.metric(label, "n/d" if m[key] is None else f"{m[key]:g} min", help=help_text)

    inc = result.incident
    tl = pd.DataFrame([{"ora": e.time.strftime("%H:%M"), "fase": e.phase, "fonte": e.phase_source, "evento": e.text} for e in inc.timeline])
    st.subheader("Timeline")
    st.dataframe(tl, use_container_width=True, hide_index=True)

    if inc.metrics:
        st.subheader("Metriche")
        df = pd.DataFrame([{"serie": f"{s.name} ({s.unit})", "ora": p.time, "valore": p.value} for s in inc.metrics for p in s.points])
        fig = px.line(df, x="ora", y="valore", color="serie", markers=True, facet_row="serie", height=220 * len(inc.metrics))
        fig.update_yaxes(matches=None)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Report")
    st.markdown(result.markdown)
    st.download_button("💾 Scarica .md", result.markdown, file_name=f"{inc.incident_id}_postmortem.md", mime="text/markdown")


if view == "Post-mortem":
    st.header("Post-mortem di un incidente")
    up = st.file_uploader("File YAML dell'incidente", type=["yaml", "yml"])
    if up:
        try:
            inc = parser.load(up.getvalue())
        except parser.IncidentParseError as exc:
            st.error(f"File non valido: {exc}")
            st.stop()
        with st.expander("YAML caricato"):
            st.code(up.getvalue().decode("utf-8"), language="yaml")
        if st.button("Analizza", type="primary"):
            with st.spinner("Analisi in corso…"):
                try:
                    result = pipeline.analyse(inc, client_or_none(use_ai, redact), language)
                except Exception as exc:  # show provider errors instead of a stack trace
                    st.error(f"Errore durante l'analisi: {exc}")
                    st.stop()
            show_analysis(result)

elif view == "Da note grezze":
    st.header("Dalle note grezze al file dell'incidente")
    st.write("Incolla export di Slack/Teams, appunti, righe di log. L'IA prepara il YAML: controllalo prima di analizzarlo.")
    raw = st.text_area("Materiale grezzo", height=300)
    date = st.text_input("Data dell'incidente (se il testo ha solo gli orari)", placeholder="2026-11-14")
    if st.button("Prepara YAML", type="primary", disabled=not raw.strip()):
        client = client_or_none(True, redact)
        with st.spinner("Estrazione…"):
            try:
                inc = extract.to_incident(extract.extract(raw, client, date))
            except Exception as exc:
                st.error(f"Estrazione non riuscita: {exc}")
                st.stop()
        y = extract.to_yaml(inc)
        st.code(y, language="yaml")
        st.download_button("💾 Scarica YAML", y, file_name=f"{inc.incident_id}.yaml", mime="text/yaml")

else:
    st.header("Dashboard multi-incidente")
    files = st.file_uploader("Uno o più file YAML", type=["yaml", "yml"], accept_multiple_files=True)
    incidents = []
    for f in files or []:
        try:
            incidents.append(parser.load(f.getvalue()))
        except parser.IncidentParseError as exc:
            st.warning(f"{f.name}: {exc}")
    if incidents:
        rows = pipeline.dashboard_rows(incidents)
        agg = pipeline.aggregate(rows)
        cols = st.columns(4)
        for col, key in zip(cols, ["TTD (min)", "TTA (min)", "TTM (min)", "TTR (min)"], strict=True):
            v = agg[key]
            label = "MTTR" if key == "TTR (min)" else f"Media {key.split()[0]}"
            col.metric(label, "n/d" if v["mean"] is None else f"{v['mean']:g} min", help=f"mediana {v['median']} · n={v['n']}")
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("⬇️ CSV", df.to_csv(index=False).encode("utf-8"), file_name="incidents.csv", mime="text/csv")
        long = df.melt(
            id_vars="incident", value_vars=["TTD (min)", "TTA (min)", "TTM (min)", "TTR (min)"], var_name="metrica", value_name="minuti"
        )
        st.plotly_chart(px.bar(long, x="incident", y="minuti", color="metrica", barmode="group"), use_container_width=True)
