# Eco-Loop Building Agents

An autonomous AI-driven building energy optimization system, acting as a Proof-of-Concept (PoC) for the Honeywell Hackathon. It pairs **EnergyPlus** with **Qwen 2.5 (via Ollama)** using the **Model Context Protocol (MCP)** to create a dynamic feedback loop for real-time energy savings.

## 🌟 Features

*   **Autonomous Closed-Loop Control**: Ingests real-time sensor data from EnergyPlus, reasons using an open-source LLM, and injects optimal setpoints back into the simulation without human intervention.
*   **MCP Protocol Integration**: Uses the official `mcp` Python SDK (FastMCP) to expose 9 discrete tools to the LLM agent, allowing it to read sensors and actuate building controls.
*   **Energy Conservation Measures (ECMs)**: Implements strategies like night setback, peak demand avoidance, occupancy-based control, and dead-band widening.
*   **Thermal Comfort Constraints**: Balances energy savings against human comfort by tracking the Predicted Mean Vote (PMV) index and keeping it within acceptable bounds (-0.5 to +0.5).
*   **Savings Dashboard**: Includes a premium, responsive HTML/JS/CSS dashboard to visualize real-time metrics, energy savings, zone temperatures, and a live log of the agent's decisions.

## 🏆 Hackathon Deliverables

This repository fulfills all requirements for the Honeywell Physical AI Proof-of-Concept:
1. **Fully Functional Source Code**: Unified Python codebase (`src/`) managing the EnergyPlus API wrapper, MCP server, and LLM agent orchestration.
2. **Building Models**: The base `.idf` and weather files are located in `models/`. Modified versions are generated during runtime.
3. **Quantitative Savings Dashboard**: A beautiful, responsive visual dashboard (`dashboard/index.html`) fed by live JSON telemetry to prove percentage reductions in kWh while maintaining comfort.
4. **System Architecture Document**: Detailed in [ARCHITECTURE.md](ARCHITECTURE.md), explaining tool-calling, prompt engineering, latency management, and log handling.
5. **PoC Demonstration Video**: (Insert your video link here)

## 🏗 System Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a detailed technical breakdown of the tool-calling architecture, prompt latency management, and simulation log handling.

## ⚙️ Setup & Installation

### Prerequisites
*   Python 3.10+
*   macOS (ARM64 recommended) or Linux

### Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Install EnergyPlus (v24.1.0)**:
   Ensure EnergyPlus is installed or placed in the `energyplus` directory at the project root.
3. **Install & Run Ollama**:
   Install Ollama and pull the recommended model:
   ```bash
   ollama pull qwen2.5:7b
   ollama serve
   ```
4. **Run the Pipeline**:
   Execute the main orchestrator to run both baseline and optimized simulations:
   ```bash
   python src/main.py
   ```

## 🚀 Usage

The `main.py` orchestrator supports different execution modes:

```bash
# Run the full pipeline (baseline -> optimized -> generate report)
python src/main.py --mode full

# Run only the baseline simulation (no AI control)
python src/main.py --mode baseline

# Run only the AI-controlled simulation
python src/main.py --mode optimized

# Generate the comparison report (requires both simulations to have run)
python src/main.py --mode compare
```

### Viewing the Dashboard
After running the pipeline, a `data.json` file is generated in the `dashboard` folder. Open `dashboard/index.html` in your web browser to view the savings and performance metrics.

## 📁 Repository Structure

*   `src/`: Core Python source code (agent, wrapper, MCP server, logging).
*   `models/`: EnergyPlus IDF files and weather data.
*   `dashboard/`: HTML/JS/CSS for the savings visualization dashboard.
*   `output/`: Simulation outputs, JSON reports, and CSV timeseries data.