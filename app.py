from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from distillation.ai_assistant import AIAssistant
from distillation.config import HISTORIAN_DB
from distillation.faults import FaultManager
from distillation.historian import Historian, TagBus
from distillation.plc import PLCController
from distillation.process import ProcessState
from distillation.tags import TAG_DICTIONARY

st.set_page_config(page_title="DT101 Distillation Digital Twin", layout="wide")

EQUIPMENT_OPTIONS = ["Feed system", "Column", "Condenser", "Reflux drum", "Reflux valve", "Reboiler", "Products"]
TREND_TAGS = [
    "DT101.PV.TOP_TEMP",
    "DT101.PV.BOTTOM_TEMP",
    "DT101.PV.COLUMN_PRESSURE",
    "DT101.PV.PURITY_PROXY",
    "DT101.CMD.REBOILER_DUTY",
    "DT101.CMD.CONDENSER_VALVE",
    "DT101.CMD.REFLUX_VALVE",
    "DT101.FB.REFLUX_VALVE_POSITION",
]


def init_session() -> None:
    defaults = {
        "state": ProcessState(),
        "plc": PLCController(mode="IDLE"),
        "faults": FaultManager(),
        "bus": TagBus(),
        "historian": Historian(Path(HISTORIAN_DB)),
        "last_heartbeat": datetime.now(timezone.utc),
        "active_alarms": [],
        "last_ai_response": "No recommendation requested yet.",
        "selected_equipment": "Column",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_simulation() -> None:
    db = Path(HISTORIAN_DB)
    if db.exists():
        db.unlink()
    for key in ["state", "plc", "faults", "bus", "historian", "last_heartbeat", "active_alarms", "last_ai_response"]:
        st.session_state.pop(key, None)
    init_session()


def simulation_tick() -> None:
    now = datetime.now(timezone.utc)
    faults = st.session_state.faults.apply()
    if "data_stale" not in faults:
        st.session_state.last_heartbeat = now

    plc_output = st.session_state.plc.scan(st.session_state.state.to_tags(), 1.0)
    controls = dict(plc_output.commands)
    controls["reflux_valve_feedback"] = faults.get("reflux_valve_stuck_position", plc_output.commands["reflux_valve"])
    controls["last_heartbeat"] = st.session_state.last_heartbeat

    state = st.session_state.state.step(plc_output.commands, faults, 1.0)
    tags = state.to_tags()
    if "top_temp_drift" in faults:
        tags["DT101.PV.TOP_TEMP"] += float(faults["top_temp_drift"])

    alarms = sorted(set(plc_output.alarms + st.session_state.faults.detect(tags, controls, now)))
    output_tags = {
        **tags,
        "DT101.CMD.REBOILER_DUTY": plc_output.commands["reboiler_duty"],
        "DT101.CMD.CONDENSER_VALVE": plc_output.commands["condenser_valve"],
        "DT101.CMD.REFLUX_VALVE": plc_output.commands["reflux_valve"],
        "DT101.FB.REFLUX_VALVE_POSITION": controls["reflux_valve_feedback"],
        "DT101.STATE.MODE": plc_output.mode,
        "DT101.HEARTBEAT.PLC": st.session_state.last_heartbeat.isoformat(),
    }
    output_tags.update({alarm: True for alarm in alarms})

    if "data_stale" not in faults:
        st.session_state.bus.publish(output_tags)
        st.session_state.historian.write(now, output_tags)

    st.session_state.state = state
    st.session_state.active_alarms = alarms


def inject_button(label: str, fault_name: str) -> None:
    active = fault_name in st.session_state.faults.active_faults
    if st.button(("Clear " if active else "Inject ") + label, use_container_width=True):
        st.session_state.faults.clear(fault_name) if active else st.session_state.faults.inject(fault_name)


def recent_dataframe(tags: list[str], seconds: int = 300) -> pd.DataFrame:
    rows = st.session_state.historian.query(tags, seconds=seconds)
    if not rows:
        return pd.DataFrame(columns=["timestamp", "tag", "value"])
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["numeric_value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def process_overview_svg(state: ProcessState, mode: str, alarms: list[str], selected: str) -> str:
    alarm_color = "#ef4444" if alarms else "#22c55e"
    feed_color = "#60a5fa" if state.feed_flow > 0.1 else "#94a3b8"
    pressure_color = "#ef4444" if state.column_pressure > 125 else "#60a5fa"
    valve_color = "#34d399" if state.reflux_flow >= 2.5 else "#f97316"
    purity_color = "#f97316" if state.purity_proxy < 90 else "#34d399"
    active_faults = ", ".join(sorted(st.session_state.faults.active_faults)) or "none"
    alarms_text = ", ".join(alarms) if alarms else "none"

    def stroke(name: str, normal: str) -> str:
        return "#facc15" if selected == name else normal

    def width(name: str, normal: int = 2) -> int:
        return 5 if selected == name else normal

    return f'''
<div class="scada-wrap"><svg viewBox="0 0 1080 620" width="100%" role="img" aria-label="Distillation process overview">
<defs><linearGradient id="panelBg" x1="0" x2="1" y1="0" y2="1"><stop offset="0%" stop-color="#111827"/><stop offset="100%" stop-color="#1f2937"/></linearGradient><linearGradient id="columnFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#0f766e" stop-opacity="0.35"/><stop offset="50%" stop-color="#f59e0b" stop-opacity="0.18"/><stop offset="100%" stop-color="#dc2626" stop-opacity="0.30"/></linearGradient><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#93c5fd"/></marker></defs>
<rect x="8" y="8" width="1064" height="604" rx="26" fill="url(#panelBg)" stroke="#334155" stroke-width="2"/><text x="38" y="52" fill="#e5e7eb" font-family="Consolas, monospace" font-size="26" font-weight="700">PROCESS SIM - DISTILLATION COLUMN DT-101</text><circle cx="980" cy="44" r="8" fill="{alarm_color}"/><text x="996" y="51" fill="#cbd5e1" font-family="Consolas, monospace" font-size="16">{'Alarm active' if alarms else 'Connected'}</text>
<rect x="32" y="78" width="650" height="500" rx="18" fill="#0b1220" stroke="#334155"/><rect x="708" y="78" width="332" height="500" rx="18" fill="#0b1220" stroke="#334155"/>
<rect x="58" y="250" width="110" height="110" rx="14" fill="#111827" stroke="{stroke('Feed system', '#64748b')}" stroke-width="{width('Feed system')}"/><rect x="68" y="{350 - min(state.feed_tank_level, 100) * 0.90:.1f}" width="90" height="{min(state.feed_tank_level, 100) * 0.90:.1f}" rx="8" fill="#1d4ed8" opacity="0.65"/><text x="76" y="236" fill="#e5e7eb" font-family="Consolas, monospace" font-size="15">FEED TANK</text><text x="76" y="382" fill="#cbd5e1" font-family="Consolas, monospace" font-size="13">LT-100 {state.feed_tank_level:04.1f}%</text>
<line x1="168" y1="305" x2="244" y2="305" stroke="{feed_color}" stroke-width="8" marker-end="url(#arrow)"/><circle cx="278" cy="305" r="28" fill="#1e293b" stroke="{stroke('Feed system', '#93c5fd')}" stroke-width="{width('Feed system', 3)}"/><path d="M268 289 L300 305 L268 321 Z" fill="#93c5fd"/><text x="250" y="353" fill="#cbd5e1" font-family="Consolas, monospace" font-size="13">P-101</text><line x1="306" y1="305" x2="390" y2="305" stroke="#93c5fd" stroke-width="8" marker-end="url(#arrow)"/><text x="315" y="286" fill="#cbd5e1" font-family="Consolas, monospace" font-size="12">FT-101 {state.feed_flow:04.1f} L/min</text>
<rect x="390" y="155" width="120" height="310" rx="28" fill="url(#columnFill)" stroke="{stroke('Column', '#e5e7eb')}" stroke-width="{width('Column', 3)}"/><line x1="390" y1="230" x2="510" y2="230" stroke="#94a3b8"/><line x1="390" y1="305" x2="510" y2="305" stroke="#94a3b8"/><line x1="390" y1="380" x2="510" y2="380" stroke="#94a3b8"/><text x="397" y="142" fill="#e5e7eb" font-family="Consolas, monospace" font-size="15">DISTILLATION COLUMN</text><text x="418" y="185" fill="#e0f2fe" font-family="Consolas, monospace" font-size="13">TT-101 {state.top_temperature:04.1f} C</text><text x="418" y="314" fill="#e0f2fe" font-family="Consolas, monospace" font-size="13">TT-102 {state.mid_temperature:04.1f} C</text><text x="418" y="445" fill="#fee2e2" font-family="Consolas, monospace" font-size="13">TT-103 {state.bottom_temperature:04.1f} C</text><text x="523" y="304" fill="{pressure_color}" font-family="Consolas, monospace" font-size="13">PT-101 {state.column_pressure:05.1f} kPa</text>
<rect x="365" y="495" width="170" height="52" rx="18" fill="#3f1d1d" stroke="{stroke('Reboiler', '#f97316')}" stroke-width="{width('Reboiler')}"/><path d="M388 520 C408 493,432 548,456 520 S506 493,526 520" fill="none" stroke="#fb923c" stroke-width="4"/><line x1="450" y1="465" x2="450" y2="495" stroke="#fb923c" stroke-width="7" marker-end="url(#arrow)"/><text x="391" y="573" fill="#fed7aa" font-family="Consolas, monospace" font-size="13">REB-101 duty {st.session_state.bus.tags.get('DT101.CMD.REBOILER_DUTY', 0):04.1f}%</text>
<line x1="450" y1="155" x2="450" y2="102" stroke="#93c5fd" stroke-width="7"/><line x1="450" y1="102" x2="590" y2="102" stroke="#93c5fd" stroke-width="7" marker-end="url(#arrow)"/><rect x="590" y="78" width="70" height="48" rx="12" fill="#082f49" stroke="{stroke('Condenser', '#60a5fa')}" stroke-width="{width('Condenser')}"/><path d="M600 91 L650 113 M650 91 L600 113" stroke="#bae6fd" stroke-width="3"/><text x="585" y="65" fill="#cbd5e1" font-family="Consolas, monospace" font-size="13">COND-101</text><line x1="660" y1="102" x2="660" y2="170" stroke="#93c5fd" stroke-width="7" marker-end="url(#arrow)"/>
<rect x="600" y="170" width="120" height="62" rx="24" fill="#172554" stroke="{stroke('Reflux drum', '#93c5fd')}" stroke-width="{width('Reflux drum')}"/><rect x="613" y="{220 - min(state.reflux_drum_level, 100) * 0.38:.1f}" width="94" height="{min(state.reflux_drum_level, 100) * 0.38:.1f}" rx="12" fill="#38bdf8" opacity="0.55"/><text x="606" y="253" fill="#cbd5e1" font-family="Consolas, monospace" font-size="12">LT-101 {state.reflux_drum_level:04.1f}%</text><line x1="600" y1="202" x2="510" y2="202" stroke="{valve_color}" stroke-width="7" marker-end="url(#arrow)"/><polygon points="555,188 580,202 555,216 530,202" fill="#064e3b" stroke="{stroke('Reflux valve', '#34d399')}" stroke-width="{width('Reflux valve')}"/><text x="522" y="181" fill="#bbf7d0" font-family="Consolas, monospace" font-size="12">V-101 {state.reflux_flow:03.1f}</text>
<line x1="720" y1="202" x2="772" y2="202" stroke="#93c5fd" stroke-width="7" marker-end="url(#arrow)"/><rect x="776" y="170" width="82" height="64" rx="14" fill="#111827" stroke="{stroke('Products', '#60a5fa')}" stroke-width="{width('Products')}"/><text x="783" y="157" fill="#e5e7eb" font-family="Consolas, monospace" font-size="13">DISTILLATE</text><line x1="510" y1="438" x2="612" y2="438" stroke="#fb923c" stroke-width="7" marker-end="url(#arrow)"/><polygon points="566,424 591,438 566,452 541,438" fill="#431407" stroke="{stroke('Products', '#fb923c')}" stroke-width="{width('Products')}"/><rect x="616" y="406" width="84" height="64" rx="14" fill="#111827" stroke="{stroke('Products', '#fb923c')}" stroke-width="{width('Products')}"/><text x="610" y="393" fill="#fed7aa" font-family="Consolas, monospace" font-size="13">BOTTOMS</text><text x="410" y="482" fill="#fed7aa" font-family="Consolas, monospace" font-size="12">LT-102 {state.bottom_sump_level:04.1f}%</text>
<text x="734" y="120" fill="#e5e7eb" font-family="Consolas, monospace" font-size="18" font-weight="700">CONTROLS</text><rect x="734" y="140" width="260" height="54" rx="12" fill="#1f2937" stroke="#475569"/><text x="756" y="173" fill="#cbd5e1" font-family="Consolas, monospace" font-size="16">PUMP P-101</text><text x="912" y="173" fill="{feed_color}" font-family="Consolas, monospace" font-size="16">AUTO</text><rect x="734" y="207" width="260" height="54" rx="12" fill="#064e3b" stroke="#34d399"/><text x="756" y="240" fill="#d1fae5" font-family="Consolas, monospace" font-size="16">VALVE V-101</text><text x="902" y="240" fill="#d1fae5" font-family="Consolas, monospace" font-size="16">{st.session_state.bus.tags.get('DT101.FB.REFLUX_VALVE_POSITION', 50):04.1f}%</text>
<text x="734" y="312" fill="#e5e7eb" font-family="Consolas, monospace" font-size="18" font-weight="700">SENSORS</text><text x="752" y="350" fill="#cbd5e1" font-family="Consolas, monospace" font-size="16">LT-101</text><text x="910" y="350" fill="#e5e7eb" font-family="Consolas, monospace" font-size="16">{state.reflux_drum_level:05.1f} %</text><text x="752" y="383" fill="#cbd5e1" font-family="Consolas, monospace" font-size="16">FT-101</text><text x="910" y="383" fill="#e5e7eb" font-family="Consolas, monospace" font-size="16">{state.feed_flow:05.2f} L/min</text><text x="752" y="416" fill="#cbd5e1" font-family="Consolas, monospace" font-size="16">FR-101</text><text x="910" y="416" fill="#e5e7eb" font-family="Consolas, monospace" font-size="16">{state.reflux_flow:05.2f} L/min</text><text x="752" y="449" fill="#cbd5e1" font-family="Consolas, monospace" font-size="16">PT-101</text><text x="910" y="449" fill="{pressure_color}" font-family="Consolas, monospace" font-size="16">{state.column_pressure:05.1f} kPa</text><text x="752" y="482" fill="#cbd5e1" font-family="Consolas, monospace" font-size="16">QI-101</text><text x="910" y="482" fill="{purity_color}" font-family="Consolas, monospace" font-size="16">{state.purity_proxy:05.1f} %</text>
<rect x="734" y="520" width="260" height="36" rx="10" fill="#111827" stroke="#334155"/><text x="748" y="543" fill="#94a3b8" font-family="Consolas, monospace" font-size="13">Mode: {mode}</text><text x="40" y="82" fill="#facc15" font-family="Consolas, monospace" font-size="13">Focus: {selected}</text><text x="40" y="602" fill="#94a3b8" font-family="Consolas, monospace" font-size="13">Faults: {active_faults} | Alarms: {alarms_text}</text>
</svg></div>'''


def equipment_profile(state: ProcessState, selected: str) -> dict[str, object]:
    profiles = {
        "Feed system": ("Supplies the binary mixture into the column and creates the main process load.", {"Feed tank level": f"{state.feed_tank_level:.1f} %", "Feed flow": f"{state.feed_flow:.2f} L/min", "Feed light fraction": f"{state.feed_composition_light:.2f}"}, "Feed pump and feed valve define column throughput.", "Feed composition disturbance changes the column temperature profile and purity proxy."),
        "Column": ("Performs vapor-liquid contacting so light material enriches overhead and heavy material enriches bottoms.", {"Top temperature": f"{state.top_temperature:.1f} degC", "Mid temperature": f"{state.mid_temperature:.1f} degC", "Bottom temperature": f"{state.bottom_temperature:.1f} degC", "Pressure": f"{state.column_pressure:.1f} kPa"}, "Pressure, reflux, and reboiler duty shape the temperature profile.", "Top temperature sensor drift is detected by inconsistency with pressure, reflux flow, and purity proxy."),
        "Condenser": ("Removes overhead heat, condenses vapor, and helps control column pressure.", {"Cooling water flow": f"{state.cooling_water_flow:.2f} L/min", "Column pressure": f"{state.column_pressure:.1f} kPa"}, "PIC101 adjusts condenser valve opening to stabilize pressure.", "Insufficient cooling would raise pressure and can lead to safety interlock action."),
        "Reflux drum": ("Buffers condensed liquid before splitting it into distillate product and reflux return.", {"Reflux drum level": f"{state.reflux_drum_level:.1f} %", "Distillate flow": f"{state.distillate_flow:.2f} L/min", "Reflux flow": f"{state.reflux_flow:.2f} L/min"}, "LIC101 adjusts distillate valve to keep reflux drum level near setpoint.", "A level excursion can indicate imbalance between condensation, reflux, and product withdrawal."),
        "Reflux valve": ("Returns liquid to the column top to improve separation quality.", {"Reflux flow": f"{state.reflux_flow:.2f} L/min", "Purity proxy": f"{state.purity_proxy:.1f} %"}, "TIC102 adjusts reflux valve based on top temperature / purity proxy.", "Reflux valve stuck is detected by command-feedback mismatch and low reflux flow."),
        "Reboiler": ("Adds heat at the column bottom to generate boil-up vapor.", {"Bottom temperature": f"{state.bottom_temperature:.1f} degC", "Bottom sump level": f"{state.bottom_sump_level:.1f} %", "Pressure": f"{state.column_pressure:.1f} kPa"}, "TIC101 adjusts reboiler duty; safety interlock cuts duty on high-high pressure or low-low bottom level.", "Excess duty can increase pressure; dry heating must be prevented by PLC interlock."),
        "Products": ("Collects distillate overhead product and bottoms heavy product.", {"Distillate tank": f"{state.distillate_tank_level:.1f} %", "Bottoms tank": f"{state.bottoms_tank_level:.1f} %", "Purity proxy": f"{state.purity_proxy:.1f} %"}, "Distillate and bottoms valves balance inventory while product quality is monitored.", "Off-spec product can be inferred from purity proxy and temperature profile deviation."),
    }
    role, watch, control, fault_link = profiles[selected]
    return {"role": role, "watch": watch, "control": control, "fault_link": fault_link}


def deepseek_api_key() -> str | None:
    try:
        return st.secrets.get("DEEPSEEK_API_KEY")
    except Exception:
        return None


init_session()
st.title("DT101 Chemical Distillation Column Digital Twin")
st.caption("Simplified binary distillation column with PLC-style control, local historian, fault injection, and DeepSeek operator assistance.")

with st.sidebar:
    st.header("Simulation")
    ticks = st.slider("Advance ticks", 1, 30, 5)
    if st.button("Run selected ticks", type="primary", use_container_width=True):
        for _ in range(ticks):
            simulation_tick()
    if st.button("Single PLC scan + process tick", use_container_width=True):
        simulation_tick()
    if st.button("Reset simulation", use_container_width=True):
        reset_simulation()
    st.divider()
    st.header("Fault injection")
    inject_button("top temperature sensor drift", "top_temp_drift")
    inject_button("reflux valve stuck", "reflux_valve_stuck")
    inject_button("feed composition disturbance", "feed_composition_disturbance")
    inject_button("data staleness", "data_stale")
    if st.button("Clear all faults", use_container_width=True):
        st.session_state.faults.clear_all()

state = st.session_state.state
mode = st.session_state.plc.mode
alarms = st.session_state.active_alarms
cols = st.columns(6)
for col, label, value in zip(cols, ["Mode", "Top temp", "Bottom temp", "Pressure", "Purity proxy", "Active alarms"], [mode, f"{state.top_temperature:.1f} degC", f"{state.bottom_temperature:.1f} degC", f"{state.column_pressure:.1f} kPa", f"{state.purity_proxy:.1f}%", len(alarms)]):
    col.metric(label, value)
st.error("Active alarms: " + ", ".join(alarms)) if alarms else st.success("No active alarms.")

st.markdown("""
<style>.scada-wrap{border-radius:22px;overflow:hidden;border:1px solid #334155;box-shadow:0 18px 45px rgba(0,0,0,.28);background:#0b1220}.equipment-card{border:1px solid #334155;border-radius:18px;padding:18px 20px;background:linear-gradient(135deg,rgba(15,23,42,.98),rgba(30,41,59,.82))}.equipment-card h4{margin:0 0 6px 0;color:#facc15}.equipment-card p{margin:8px 0}</style>
""", unsafe_allow_html=True)

st.subheader("Interactive process overview")
st.session_state.selected_equipment = st.radio("Focus equipment", EQUIPMENT_OPTIONS, index=EQUIPMENT_OPTIONS.index(st.session_state.selected_equipment), horizontal=True, label_visibility="collapsed")
st.markdown(process_overview_svg(state, mode, alarms, st.session_state.selected_equipment), unsafe_allow_html=True)
profile = equipment_profile(state, st.session_state.selected_equipment)
detail_col, values_col = st.columns([1.2, 1.0])
with detail_col:
    st.markdown(f'<div class="equipment-card"><h4>{st.session_state.selected_equipment}</h4><p><strong>Role:</strong> {profile["role"]}</p><p><strong>Control meaning:</strong> {profile["control"]}</p><p><strong>Fault link:</strong> {profile["fault_link"]}</p></div>', unsafe_allow_html=True)
with values_col:
    st.dataframe(pd.DataFrame([{"Variable": k, "Live value": v} for k, v in profile["watch"].items()]), use_container_width=True, hide_index=True)

overview_tab, faults_tab, tags_tab = st.tabs(["Live variables", "Faults", "Tag dictionary"])
with overview_tab:
    st.dataframe(pd.DataFrame({"Variable": ["Feed flow (L/min)", "Reflux flow (L/min)", "Distillate flow (L/min)", "Bottoms flow (L/min)", "Reflux drum level (%)", "Bottom sump level (%)", "Feed composition light fraction"], "Value": [state.feed_flow, state.reflux_flow, state.distillate_flow, state.bottoms_flow, state.reflux_drum_level, state.bottom_sump_level, state.feed_composition_light]}), use_container_width=True)
with faults_tab:
    st.write("Active faults:", sorted(st.session_state.faults.active_faults) or "none")
    st.write("Active alarms:", alarms or "none")
with tags_tab:
    st.dataframe(pd.DataFrame([{"Tag": m.name, "Description": m.description, "Unit": m.unit, "Normal": m.normal_range, "Alarm": m.alarm_limits} for m in TAG_DICTIONARY.values()]), use_container_width=True, hide_index=True)

st.subheader("Historian trends")
df = recent_dataframe(TREND_TAGS, seconds=600)
if df.empty:
    st.info("Run a few ticks to populate historian trends.")
else:
    st.plotly_chart(px.line(df.dropna(subset=["numeric_value"]), x="timestamp", y="numeric_value", color="tag"), use_container_width=True)

st.subheader("AI operator assistant")
history = st.session_state.historian.query(TREND_TAGS, seconds=120)
alarm_context = {"mode": mode, "active_alarms": alarms, "active_faults": sorted(st.session_state.faults.active_faults), "heartbeat_age_seconds": (datetime.now(timezone.utc) - st.session_state.last_heartbeat).total_seconds()}
if st.button("Ask DeepSeek assistant", use_container_width=True):
    st.session_state.last_ai_response = AIAssistant(api_key=deepseek_api_key()).recommend(alarm_context, history)
st.text_area("Recommendation", st.session_state.last_ai_response, height=260)
st.caption("Data staleness fault intentionally freezes broker/historian writes while the underlying process can continue locally.")
