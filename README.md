# DT101 Distillation Digital Twin

This project implements a Python/Streamlit digital twin for a simplified continuous binary distillation column. It follows the assignment concept in `Distillation_Processing_Introduction_EN.md`: process model, PLC-style control, local broker/historian simulation, fault injection, dashboard trends, and a DeepSeek-powered operator assistant.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Optional DeepSeek configuration:

```powershell
$env:DEEPSEEK_API_KEY="your_api_key"
$env:DEEPSEEK_MODEL="deepseek-v4-flash"
```

Alternatively, create `.streamlit/secrets.toml` locally:

```toml
DEEPSEEK_API_KEY = "your_api_key"
```

If `DEEPSEEK_API_KEY` is not set or the API call fails, the AI assistant returns a deterministic structured fallback recommendation.

## Architecture

```text
Digital process simulator
    -> simulated sensors and actuators
    -> PLC/control layer
    -> in-memory tag bus
    -> SQLite historian
    -> Streamlit dashboard
    -> DeepSeek AI assistant
```

The local stack intentionally simulates MQTT/OPC-UA and historian behavior without requiring external services. This keeps the demo reliable while preserving the ISA-95 / Industry 4.0 data-flow story.

## Main files

- `app.py`: Streamlit UI, fault injection controls, trends, alarms, AI assistant panel.
- `distillation/process.py`: simplified binary distillation process model.
- `distillation/plc.py`: PLC scan cycle, PID loops, state machine, safety interlocks.
- `distillation/faults.py`: sensor, equipment, process, and infrastructure fault detection.
- `distillation/historian.py`: in-memory tag bus and SQLite historian.
- `distillation/ai_assistant.py`: DeepSeek client, prompt builder, deterministic fallback.
- `tests/`: pytest coverage for process dynamics, PLC interlocks, faults, historian, and AI prompt behavior.

## PLC behavior

The controller follows a scan-cycle model:

```text
Read inputs -> Execute state/PID/interlock logic -> Update outputs
```

State machine:

```text
IDLE -> FILLING -> STARTUP_HEATING -> STABILIZING -> NORMAL_OPERATION -> FAULT_HANDLING -> SHUTDOWN
```

Implemented PID-like loops:

- `PIC101`: column pressure -> condenser cooling valve.
- `TIC101`: bottom temperature -> reboiler duty.
- `TIC102`: top temperature / purity proxy -> reflux valve.
- `LIC101`: reflux drum level -> distillate valve.
- `LIC102`: bottom sump level -> bottoms valve.

Safety interlocks are handled locally in the PLC layer. High-high pressure forces reboiler duty to zero, condenser valve to full open, feed pump off, and mode `SHUTDOWN`.

## Fault catalog

| Layer | Fault | Alarm |
| --- | --- | --- |
| Sensor | Top temperature sensor drift | `DT101.ALARM.TOP_TEMP_SENSOR_DRIFT` |
| Equipment | Reflux valve stuck partially closed | `DT101.ALARM.REFLUX_VALVE_STUCK` |
| Process | Feed composition disturbance | `DT101.ALARM.FEED_COMPOSITION_DISTURBANCE` |
| Infrastructure | Broker/historian data staleness | `DT101.ALARM.DATA_STALE` |

Each fault is visible in the dashboard and is designed to produce detectable evidence within 60 simulated seconds.

## Demo script

1. Run several ticks until the historian has trend data.
2. Explain the process overview: feed, column, reboiler, condenser, reflux drum, products.
3. Inject `top temperature sensor drift`; show inconsistent top temperature versus reflux/pressure/purity.
4. Inject `reflux valve stuck`; show command-feedback mismatch and purity degradation.
5. Inject `feed composition disturbance`; show temperature profile and purity response.
6. Inject `data staleness`; show heartbeat age and frozen historian/dashboard data.
7. Ask the DeepSeek assistant for a recommendation and explain the safety boundary: AI recommends, PLC controls.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The tests cover:

- Reflux loss, reboiler duty, and condenser pressure behavior.
- PLC high-high pressure shutdown and bounded normal commands.
- Four fault-detection paths.
- SQLite historian writes and queries.
- AI prompt safety content and fallback recommendation.
