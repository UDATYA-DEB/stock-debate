"""Stock Debate UI.

Run with:  .venv/bin/streamlit run stockdebate/ui/app.py

Flow: setup (Gemini key + two endpoints) -> health check -> main screen.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from pydantic import SecretStr

from stockdebate.llm import config as cfg
from stockdebate.llm import health

st.set_page_config(page_title="Stock Debate", page_icon="⚖️", layout="wide")

DISCLAIMER = "Research and learning project. Not financial advice."


def _state():
    st.session_state.setdefault("config", None)
    st.session_state.setdefault("health", None)
    st.session_state.setdefault("ready", False)


@st.cache_resource(show_spinner=False)
def get_obs(public_key: str | None, secret_key: str | None, host: str | None):
    from stockdebate.obs.tracing import Observability
    return Observability.from_keys(public_key, secret_key, host)


# ---------- setup screen ----------

def endpoint_picker(role: str, title: str, saved: dict, default_model: str,
                    token: str | None = None) -> tuple[str, str | None]:
    """URL input + 'List models' button + model dropdown. Returns (url, selected model)."""
    url = st.text_input(title, value=saved.get(f"{role}_url", ""),
                        placeholder=cfg.PLACEHOLDERS[f"{role}_url"], key=f"{role}_url")
    listed_key, listed_url_key = f"{role}_models", f"{role}_models_url"

    if st.button("List models", key=f"{role}_list"):
        with st.spinner("Fetching models..."):
            result = health.list_models(url, token)
        if result.error:
            st.session_state[listed_key] = []
            st.error(result.error)
        else:
            st.session_state[listed_key] = result.models
            st.session_state[listed_url_key] = url.strip()

    models = st.session_state.get(listed_key, [])
    if models and st.session_state.get(listed_url_key) != url.strip():
        st.warning("The URL changed since the models were listed. List them again.")
        return url, None
    if not models:
        st.caption("Enter the URL and click **List models** to choose a model.")
        return url, None

    preferred = saved.get(f"{role}_model", default_model)
    index = models.index(preferred) if preferred in models else 0
    model = st.selectbox(f"{role.capitalize()} model", models, index=index, key=f"{role}_model")
    return url, model


def setup_screen() -> None:
    st.title("Stock Debate: setup")
    st.caption(DISCLAIMER)
    st.write("Connect the three models. All three must pass the health check before you can start.")

    saved = cfg.load_saved()

    st.subheader("Judge")
    gemini_key = st.text_input("Gemini API key", type="password",
                               value=saved.get("gemini_api_key", ""),
                               placeholder=cfg.PLACEHOLDERS["gemini_api_key"])
    with st.expander("Advanced: judge model"):
        judge_model = st.text_input("Judge model", value=saved.get("judge_model", cfg.DEFAULT_JUDGE_MODEL),
                                    help="If this model isn't available, the health check lists options.")

    st.subheader("Debaters")
    col_bull, col_bear = st.columns(2)
    with col_bull:
        bull_url, bull_model = endpoint_picker(
            role="bull", title="Bull agent endpoint (local Ollama)", saved=saved,
            default_model=cfg.DEFAULT_BULL_MODEL)
    with col_bear:
        bear_token = st.text_input("Bear endpoint token", type="password",
                                   value=saved.get("bear_token", ""),
                                   placeholder=cfg.PLACEHOLDERS["bear_token"])
        bear_url, bear_model = endpoint_picker(
            role="bear", title="Bear agent endpoint (Kaggle notebook)", saved=saved,
            default_model=cfg.DEFAULT_BEAR_MODEL, token=bear_token.strip() or None)

    st.subheader("Observability (Langfuse)")
    st.caption("Traces every model call and manages the prompts. Optional: leave blank to "
               "run without tracing, using the built-in prompts.")
    col_pk, col_sk, col_host = st.columns(3)
    with col_pk:
        lf_public = st.text_input("Langfuse public key", value=saved.get("langfuse_public_key", ""),
                                  placeholder=cfg.PLACEHOLDERS["langfuse_public_key"])
    with col_sk:
        lf_secret = st.text_input("Langfuse secret key", type="password",
                                  value=saved.get("langfuse_secret_key", ""),
                                  placeholder=cfg.PLACEHOLDERS["langfuse_secret_key"])
    with col_host:
        lf_host = st.text_input("Langfuse host", value=saved.get("langfuse_host", ""),
                                placeholder=cfg.PLACEHOLDERS["langfuse_host"])

    st.divider()
    remember = st.checkbox("Remember these settings on this machine (saved to a local .env file)")
    ready_to_check = bool(bull_model and bear_model)
    submitted = st.button("Run health check", type="primary", disabled=not ready_to_check,
                          help=None if ready_to_check else "List and select a model for both endpoints first.")

    if submitted:
        config = cfg.RuntimeConfig(
            gemini_api_key=SecretStr(gemini_key),
            judge_model=judge_model.strip(),
            bull_url=bull_url.strip(),
            bull_model=bull_model,
            bear_url=bear_url.strip(),
            bear_model=bear_model,
            bear_token=SecretStr(bear_token) if bear_token.strip() else None,
            langfuse_public_key=lf_public.strip() or None,
            langfuse_secret_key=SecretStr(lf_secret.strip()) if lf_secret.strip() else None,
            langfuse_host=lf_host.strip() or cfg.DEFAULT_LANGFUSE_HOST,
        )
        with st.spinner("Checking all three models (the first answer can take a minute while a model loads)..."):
            results = health.check_all(config)
        st.session_state.config = config
        st.session_state.health = results
        if remember:
            path = cfg.save(config)
            st.info(f"Settings saved to {path}")

    results = st.session_state.health
    if results:
        st.subheader("Health check")
        for r in results:
            if r.ok:
                st.success(f"**{r.name}**: {r.detail}")
            else:
                st.error(f"**{r.name}**: {r.detail}")
            if r.name == health.LANGFUSE_NAME and not r.ok and r.available_models:
                if st.button("Push default prompts to Langfuse",
                             help="Creates only the missing prompts, labelled 'production'. "
                                  "Existing prompts are never overwritten."):
                    c = st.session_state.config
                    pushed = get_obs(c.langfuse_public_key, c.langfuse_secret, c.langfuse_host
                                     ).push_default_prompts()
                    st.session_state.health = health.check_all(c)
                    st.toast(f"Pushed: {', '.join(pushed) or 'nothing (already there)'}")
                    st.rerun()
        if all(r.ok for r in results):
            if st.button("Start", type="primary"):
                st.session_state.ready = True
                st.rerun()
        else:
            st.warning("Fix the failing connections and run the health check again.")


# ---------- main screen ----------

def sidebar() -> None:
    with st.sidebar:
        st.header("Connections")
        for r in st.session_state.health or []:
            st.write(f"{'✅' if r.ok else '❌'} {r.name}")
        if st.button("Recheck"):
            st.session_state.health = health.check_all(st.session_state.config)
            if not all(r.ok for r in st.session_state.health):
                st.session_state.ready = False
            st.rerun()
        if st.button("Change settings"):
            st.session_state.ready = False
            st.session_state.health = None
            st.rerun()


@st.cache_data(ttl=3600, show_spinner=False)
def analyse(symbol: str) -> dict:
    # Imported lazily so the setup screen loads fast.
    from stockdebate.data.gather import gather
    from stockdebate.data.providers.yfinance_provider import YFinanceProvider
    from stockdebate.debate.casefile import build_casefile

    data = gather(symbol, providers=[YFinanceProvider()])
    case = build_casefile(data)
    return {
        "name": case.name,
        "case": case,
        "eligibility": case.eligibility,
        "sheet": case.sheet,
        "flags": case.red_flags,
        "data_unavailable": data.unavailable,
        "quality": data.quality_issues,
    }


def opening_section(case) -> None:
    from uuid import uuid4

    from stockdebate.debate.agent import opening_round
    from stockdebate.llm.clients import make_debater

    c = st.session_state.config
    obs = get_obs(c.langfuse_public_key, c.langfuse_secret, c.langfuse_host)
    st.subheader("Opening arguments (milestone 3 preview)")
    st.caption("Each agent presents its case from the fact sheet. Every number it writes is "
               "checked against the facts it cites."
               + ("" if obs.enabled else " Langfuse is off: no traces, built-in prompts."))

    endpoints = {
        "bull": (c.bull_url, c.bull_model, None),
        "bear": (c.bear_url, c.bear_model, c.bear_token.get_secret_value() if c.bear_token else None),
    }
    cols = st.columns(2)
    for col, role in zip(cols, ("bull", "bear")):
        with col:
            url, model, token = endpoints[role]
            if st.button(f"Generate {role} opening ({model})", key=f"open_{role}"):
                with st.spinner(f"The {role} agent is thinking (can take a few minutes)..."):
                    try:
                        with obs.trace(f"opening {case.symbol}", session_id=f"{case.symbol}-{uuid4().hex[:8]}",
                                       tags=[case.symbol, role, "opening"], metadata={"model": model}):
                            turn, checks = opening_round(role, case, make_debater(url, model, token),
                                                         model, obs)
                    except Exception as exc:
                        st.error(f"The {role} agent failed: {exc}")
                        continue
                    finally:
                        obs.flush()
                st.session_state[f"opening_{role}"] = (case.symbol, turn, checks)

            stored = st.session_state.get(f"opening_{role}")
            if stored and stored[0] == case.symbol:
                show_turn(*stored[1:])


STATUS_ICON = {"supported": "✅", "misquoted": "❌", "unsupported": "❌"}


def show_turn(turn, checks) -> None:
    st.caption(f"{turn.model} · prompt {turn.prompt_source} · ~{turn.prompt_tokens_est} prompt tokens · "
               f"{turn.attempts} attempt(s) · {turn.latency_s}s")
    if turn.error:
        st.error(f"No valid output: {turn.error}")
        with st.expander("Raw output"):
            st.code(turn.raw_outputs[-1] if turn.raw_outputs else "", language="json")
        return
    st.markdown(f"**Thesis:** {turn.thesis}  \n**Case strength:** {turn.case_strength}")
    by_id = {c.claim_id: c for c in checks}
    for claim in turn.claims:
        chk = by_id[claim.id]
        rng = (f" _(forecast {claim.forecast_low}–{claim.forecast_high} {claim.forecast_unit})_"
               if claim.type == "forecast" else "")
        st.markdown(f"{STATUS_ICON[chk.status]} **{claim.id}** · {claim.type} · {claim.importance}  \n"
                    f"{claim.text}{rng}  \n"
                    f"<small>cites {', '.join(claim.citations) or 'nothing'} — {chk.status}: {chk.detail}</small>",
                    unsafe_allow_html=True)
    ok = sum(1 for c in checks if c.status == "supported")
    st.metric("Claims supported", f"{ok}/{len(checks)}")


ICON = {"pass": "✅", "fail": "❌", "unknown": "❔", "clear": "✅", "triggered": "🚩"}


def main_screen() -> None:
    sidebar()
    st.title("Stock Debate")
    st.caption(DISCLAIMER)

    with st.form("analyse"):
        symbol = st.text_input("NSE symbol", placeholder="e.g. TITAN").strip().upper()
        go = st.form_submit_button("Analyse", type="primary")
    if not (go and symbol) and "last_symbol" not in st.session_state:
        return
    if go and symbol:
        st.session_state.last_symbol = symbol
    symbol = st.session_state.last_symbol

    with st.spinner(f"Gathering data for {symbol}..."):
        try:
            result = analyse(symbol)
        except Exception as exc:  # network or provider failure
            st.error(f"Could not gather data for {symbol}: {exc}")
            return

    st.header(f"{result['name']} ({symbol})")
    elig = result["eligibility"]
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Eligibility: " + ("eligible" if elig.eligible else "not eligible"))
        for c in elig.checks:
            st.write(f"{ICON[c.status]} **{c.name}**: {c.detail}")
    with col2:
        st.subheader("Red flags")
        for f in result["flags"]:
            refs = f" ({', '.join(f.facts)})" if f.facts else ""
            st.write(f"{ICON[f.status]} **{f.description}**: {f.detail}{refs}")

    st.subheader("Fact sheet")
    sheet = result["sheet"]
    rows = [{
        "ID": f.id,
        "Fact": f.label,
        "Value": f.value,
        "Unit": f.unit,
        "Period": f.period,
        "Trend": f.trend.direction if f.trend else "",
        "Latest rank": f"{f.trend.latest_rank}/{f.trend.n_periods}" if f.trend else "",
        "History": ", ".join(f"{h.period}: {h.value:,.2f}" for h in f.history),
    } for f in sheet.facts]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    with st.expander("How each fact is calculated"):
        for f in sheet.facts:
            if f.basis:
                st.write(f"**{f.id} {f.label}**: {f.basis}")

    missing = sheet.unavailable + result["data_unavailable"]
    if missing or result["quality"]:
        with st.expander(f"Unavailable data and quality issues ({len(missing) + len(result['quality'])})"):
            for u in missing:
                st.write(f"❔ **{u.dataset}**: {u.reason}")
            for q in result["quality"]:
                st.write(f"⚠️ **{q.dataset}**: {q.issue}")

    st.divider()
    opening_section(result["case"])


_state()
if st.session_state.ready:
    main_screen()
else:
    setup_screen()
