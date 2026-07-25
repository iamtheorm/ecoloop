# Eco-Loop Building Agent — System Architecture Document

## 1. System Overview

Eco-Loop is an autonomous AI-driven closed-loop building energy optimization system that pairs **EnergyPlus** (physics-based building simulation) with an **open-source LLM** (Qwen 2.5 via Ollama) through the **Model Context Protocol (MCP)**. The system continuously monitors building performance metrics, reasons about energy-saving opportunities, and injects optimized control actions back into the running simulation — all without human intervention.

```
┌────────────────────────────────────────────────────────────────────┐
│                     ECO-LOOP ARCHITECTURE                          │
│                                                                    │
│   ┌─────────────────┐          ┌──────────────────────────┐       │
│   │   EnergyPlus    │  Sensor  │      MCP Server           │       │
│   │   v24.1.0       │  Data    │      (FastMCP)            │       │
│   │                 ├─────────►│                           │       │
│   │  • 5-Zone Office│          │  Tools:                   │       │
│   │  • Weather Data │          │  ├── read_zone_sensors    │       │
│   │  • HVAC System  │◄─────────┤  ├── read_energy_data     │       │
│   │                 │ Actuator │  ├── read_outdoor_cond    │       │
│   │  Callbacks:     │ Commands │  ├── read_pmv_comfort     │       │
│   │  • Timestep CB  │          │  ├── set_cooling_sp       │       │
│   │  • Sensor Read  │          │  ├── set_heating_sp       │       │
│   │  • Actuator Set │          │  ├── set_lighting_frac    │       │
│   └─────────────────┘          │  ├── get_sim_status       │       │
│                                │  └── compare_baseline     │       │
│                                └────────────┬─────────────┘       │
│                                             │                      │
│                                    Tool     │  Tool                │
│                                    Calls    │  Results             │
│                                             ▼                      │
│                                ┌──────────────────────────┐       │
│                                │    LLM Agent (Qwen 2.5)  │       │
│                                │    via Ollama             │       │
│                                │                           │       │
│                                │  • System Prompt          │       │
│                                │  • Tool-Calling Loop      │       │
│                                │  • Energy Strategies      │       │
│                                │  • Fallback Rules         │       │
│                                │  • Context Management     │       │
│                                └────────────┬─────────────┘       │
│                                             │                      │
│                                             ▼                      │
│                                ┌──────────────────────────┐       │
│                                │    Data Logger & Export   │       │
│                                │  • CSV/JSON Time Series   │       │
│                                │  • Agent Decision Log     │       │
│                                │  • Comparison Report      │       │
│                                │  • Dashboard Data Feed    │       │
│                                └──────────────────────────┘       │
└────────────────────────────────────────────────────────────────────┘
```

## 2. Tool-Calling Architecture

### 2.1 MCP Protocol Implementation

The MCP server is built using **FastMCP** from the official `mcp` Python SDK. It exposes 9 tools that the LLM can call to interact with the EnergyPlus simulation:

| # | Tool | Direction | Description |
|---|------|-----------|-------------|
| 1 | `read_zone_sensors` | EP → AI | Temperature, humidity, occupancy per zone |
| 2 | `read_energy_consumption` | EP → AI | Total facility, HVAC, and lighting power |
| 3 | `read_outdoor_conditions` | EP → AI | Weather data (temp, humidity, wind, solar) |
| 4 | `read_pmv_comfort` | EP → AI | Thermal comfort index with status |
| 5 | `set_cooling_setpoint` | AI → EP | Override cooling setpoint for a zone |
| 6 | `set_heating_setpoint` | AI → EP | Override heating setpoint for a zone |
| 7 | `set_lighting_fraction` | AI → EP | Override lighting power fraction |
| 8 | `get_simulation_status` | EP → AI | Current time, occupancy, energy totals |
| 9 | `compare_with_baseline` | Logger → AI | Baseline vs. optimized comparison |

### 2.2 Tool Execution Flow

```
1. EnergyPlus callback fires (end of zone timestep)
2. Sensor data collected and buffered
3. Agent receives sensor summary prompt
4. LLM reasons and selects tools to call
5. Tools execute against live simulation state
6. LLM receives tool results
7. LLM provides final reasoning and decisions
8. Actuator values applied to EnergyPlus in next timestep
```

### 2.3 Dual Execution Mode

The MCP server supports two modes:
- **Protocol Mode** (`stdio`): Full MCP protocol for integration with MCP clients
- **Direct Mode**: Functions called directly via `execute_tool()` for lower-latency agent integration

## 3. Prompt Engineering Strategies

### 3.1 System Prompt Design

The system prompt is carefully structured to:
- Define the agent's **role** as a building energy optimization engineer
- Specify **constraints** (temperature ranges, comfort bounds, safety limits)
- Provide **strategy guidelines** (night setback, pre-cooling, occupancy-based control, peak demand avoidance)
- Define the **response format** (Observation → Assessment → Actions → Reasoning)

### 3.2 Structured Sensor Summary

Rather than raw data dumps, sensor data is formatted into a human-readable markdown summary:
```markdown
## Current Building State — 07/15 at 14:00
**Occupancy Status**: OCCUPIED
**Peak Demand Period**: YES ⚠️

### Outdoor Conditions
- Temperature: 28.5°C
- Solar Radiation: 650 W/m²

### Zone Status
**SPACE1-1**:
- Temperature: 23.2°C, PMV: +0.3
- Occupants: 12
```

### 3.3 Few-Shot Examples

The prompt includes one complete example of the agent analyzing a summer afternoon scenario and making occupancy-based optimizations. This primes the model for the correct response pattern.

## 4. Prompt Latency Management

### 4.1 Context Window Control

- **History Trimming**: Conversation history is capped at 10 exchanges (20 messages). Older messages are dropped while preserving the system prompt and few-shot examples.
- **Summary Prompts**: Instead of sending raw timeseries data, sensor readings are summarized into concise natural language.
- **Agent Interval**: The LLM is consulted every 4 timesteps (1 simulated hour) rather than every 15-minute timestep, reducing API calls by 75%.

### 4.2 Latency Metrics

- Average LLM response time is tracked per decision
- Each decision is timestamped for latency analysis
- Total latency budget: ~2-5 seconds per agent decision at hourly intervals

### 4.3 Fallback Control

If the LLM errors or takes too long, a **rule-based fallback** automatically applies:
- Night setback during unoccupied hours
- Peak demand widened dead bands
- Occupancy-based zone control
- Server room safety overrides

## 5. Handling Lengthy Simulation Logs

### 5.1 Streaming Architecture

EnergyPlus runs in a separate thread with Python callbacks. Sensor data is:
1. **Buffered** in a thread-safe dict (latest values only)
2. **Queued** in a bounded queue for batch processing
3. **Logged** to the DataLogger for persistent storage

### 5.2 Data Compression

- Only **delta values** (changes) are sent to the LLM
- Zone data is **aggregated** rather than reporting individual surfaces/nodes
- Energy data uses **cumulative kWh** rather than per-timestep Joules
- Historical data is stored in CSV/JSON but never sent to the LLM context

### 5.3 Output Processing

EnergyPlus generates extensive output files. The system:
- Writes output to dedicated directories (`output/baseline_results/`, `output/optimized_results/`)
- Extracts only relevant metrics for comparison
- Generates a single `comparison_report.json` for dashboard visualization

## 6. Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Simulation Engine | EnergyPlus | 24.1.0 |
| IDF Parser | eppy | 0.5.69 |
| Python Runtime | Python | 3.10 |
| LLM | Qwen 2.5 | 7B |
| LLM Runtime | Ollama | 0.32+ |
| MCP Server | FastMCP (mcp SDK) | 1.28+ |
| Dashboard | HTML/CSS/JS + Chart.js | 4.4.0 |
| Data Processing | pandas, numpy | Latest |

## 7. Building Model

The baseline building is derived from the EnergyPlus `5ZoneAirCooled` reference model:
- **5 thermal zones** (SPACE1-1 through SPACE5-1) plus a plenum
- **Standard HVAC** with air-cooled chiller
- **Baseline setpoints**: Heating 21°C / Cooling 24°C (occupied), 16°C / 28°C (unoccupied)
- **Occupancy**: Weekday 8:00-18:00
- **Simulation period**: 1 week in summer (July 15-21)
- **Weather**: San Francisco TMY3

## 8. Energy Conservation Strategies

The agent implements the following Energy Conservation Measures (ECMs):

1. **Night Setback**: Wide dead band (16°C heating / 28°C cooling) during unoccupied hours
2. **Pre-Cooling**: Start conditioning 30 min before occupancy
3. **Occupancy-Based Control**: Reduce conditioning in low-occupancy zones
4. **Dead-Band Widening**: During mild weather, let building float naturally
5. **Peak Demand Avoidance**: Reduce HVAC load during 14:00-17:00 peak period
6. **Lighting Optimization**: Dim/off in unoccupied zones
