"""
main.py — Main orchestrator for the Eco-Loop Building Agent system.
Coordinates EnergyPlus simulation, LLM agent, and data logging.
Runs baseline and AI-controlled simulations, then generates comparison reports.
"""

import os
import sys
import json
import time
import argparse
import threading
import shutil
from typing import Optional

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.energyplus_wrapper import EnergyPlusWrapper
from src.idf_manager import create_baseline_office_idf, IDFManager
from src.mcp_server import set_ep_wrapper, set_data_logger, set_sim_status, execute_tool
from src.agent import EcoLoopAgent
from src.data_logger import DataLogger

# EnergyPlus paths
EP_PATH = os.path.join(PROJECT_ROOT, "energyplus")
EPW_FILE = os.path.join(EP_PATH, "WeatherData",
                        "USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw")
IDF_FILE = os.path.join(PROJECT_ROOT, "models", "baseline_office.idf")


def run_baseline_simulation(data_logger: DataLogger, 
                             ep_path: str = EP_PATH,
                             idf_path: str = IDF_FILE,
                             epw_path: str = EPW_FILE) -> bool:
    """
    Run the baseline simulation (no AI control).
    Uses default fixed setpoints from the IDF file.
    """
    print("\n" + "="*70)
    print("  PHASE 1: BASELINE SIMULATION (No AI Control)")
    print("="*70)
    
    data_logger.set_mode("baseline")
    
    # Create the wrapper
    wrapper = EnergyPlusWrapper(ep_path)
    zone_names = ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]
    wrapper.set_zone_names(zone_names)
    
    # Set up MCP server references
    set_ep_wrapper(wrapper)
    set_data_logger(data_logger)
    
    # Logging callback — records sensor data each timestep
    def baseline_callback(sensor_data, timestep):
        for zone_name, zone_data in sensor_data.get("zones", {}).items():
            data_logger.log_sensor_reading(
                timestep=timestep,
                sim_time_hours=timestep * 0.25,
                zone_name=zone_name,
                data={
                    "zone_temp_c": zone_data.get("temp_c", 0),
                    "humidity_ratio": zone_data.get("humidity_ratio", 0),
                    "occupancy": zone_data.get("occupancy", 0),
                    "pmv": zone_data.get("pmv", 0),
                    "heating_sp": zone_data.get("heating_sp", 21),
                    "cooling_sp": zone_data.get("cooling_sp", 24),
                    "total_energy_kwh": sensor_data.get("energy", {}).get("total_energy_kwh", 0),
                    "hvac_w": sensor_data.get("energy", {}).get("hvac_w", 0),
                    "outdoor_temp_c": sensor_data.get("outdoor", {}).get("temp_c", 0),
                }
            )
        
        # Progress reporting
        if timestep % 96 == 0:  # Every 24 hours (96 timesteps at 15-min intervals)
            hour = sensor_data.get("sim_hour", 0)
            day = sensor_data.get("sim_day", 0)
            month = sensor_data.get("sim_month", 0)
            energy = sensor_data.get("energy", {}).get("cumulative_kwh", 0)
            print(f"  [Baseline] Day {day}, Hour {hour:02d} — "
                  f"Cumulative: {energy:.1f} kWh")
    
    wrapper.set_on_timestep_callback(baseline_callback)
    
    # Run simulation
    output_dir = os.path.join(PROJECT_ROOT, "output", "baseline_results")
    success = wrapper.run_simulation(
        idf_path=idf_path,
        epw_path=epw_path,
        output_dir=output_dir,
        enable_control=True  # Need callbacks for data collection
    )
    
    if success:
        baseline_kwh = data_logger.get_baseline_energy_total()
        print(f"\n  [Baseline] ✅ Complete — Total Energy: {baseline_kwh:.2f} kWh")
    else:
        print(f"\n  [Baseline] ❌ Simulation failed!")
    
    return success


def run_optimized_simulation(data_logger: DataLogger,
                              model: str = "qwen2.5:7b",
                              ep_path: str = EP_PATH,
                              idf_path: str = IDF_FILE,
                              epw_path: str = EPW_FILE) -> bool:
    """
    Run the AI-controlled simulation with LLM agent making decisions.
    """
    print("\n" + "="*70)
    print("  PHASE 2: AI-CONTROLLED SIMULATION (Eco-Loop Agent)")
    print("="*70)
    
    data_logger.set_mode("optimized")
    
    # Create fresh wrapper
    wrapper = EnergyPlusWrapper(ep_path)
    zone_names = ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]
    wrapper.set_zone_names(zone_names)
    
    # Set up MCP server references
    set_ep_wrapper(wrapper)
    set_data_logger(data_logger)
    
    # Create the AI agent
    agent = EcoLoopAgent(model=model, data_logger=data_logger)
    
    # Agent decision interval (every N timesteps)
    # At 4 timesteps/hour, every 4 timesteps = 1 hour
    AGENT_INTERVAL = 4
    
    def optimized_callback(sensor_data, timestep):
        # Log sensor data
        for zone_name, zone_data in sensor_data.get("zones", {}).items():
            data_logger.log_sensor_reading(
                timestep=timestep,
                sim_time_hours=timestep * 0.25,
                zone_name=zone_name,
                data={
                    "zone_temp_c": zone_data.get("temp_c", 0),
                    "humidity_ratio": zone_data.get("humidity_ratio", 0),
                    "occupancy": zone_data.get("occupancy", 0),
                    "pmv": zone_data.get("pmv", 0),
                    "heating_sp": zone_data.get("heating_sp", 21),
                    "cooling_sp": zone_data.get("cooling_sp", 24),
                    "total_energy_kwh": sensor_data.get("energy", {}).get("total_energy_kwh", 0),
                    "hvac_w": sensor_data.get("energy", {}).get("hvac_w", 0),
                    "outdoor_temp_c": sensor_data.get("outdoor", {}).get("temp_c", 0),
                }
            )
        
        # Run agent at intervals
        if timestep % AGENT_INTERVAL == 0 and timestep > 0:
            hour = sensor_data.get("sim_hour", 0)
            day = sensor_data.get("sim_day", 0)
            print(f"\n  [Loop] Day {day}, Hour {hour:02d} — Agent thinking...")
            
            result = agent.analyze_and_act(sensor_data, timestep)
            
            if result.get("errors"):
                print(f"  [Loop] ⚠️ Agent errors: {result['errors']}")
        
        # Progress reporting
        if timestep % 96 == 0:
            energy = sensor_data.get("energy", {}).get("cumulative_kwh", 0)
            day = sensor_data.get("sim_day", 0)
            hour = sensor_data.get("sim_hour", 0)
            print(f"\n  [Optimized] Day {day}, Hour {hour:02d} — "
                  f"Cumulative: {energy:.1f} kWh")
    
    wrapper.set_on_timestep_callback(optimized_callback)
    
    # Run simulation
    output_dir = os.path.join(PROJECT_ROOT, "output", "optimized_results")
    success = wrapper.run_simulation(
        idf_path=idf_path,
        epw_path=epw_path,
        output_dir=output_dir,
        enable_control=True
    )
    
    if success:
        optimized_kwh = data_logger.get_optimized_energy_total()
        savings_pct = data_logger.get_energy_savings_percent()
        print(f"\n  [Optimized] ✅ Complete — Total Energy: {optimized_kwh:.2f} kWh")
        print(f"  [Optimized] 📊 Agent stats: {agent.stats}")
        print(f"  [Optimized] 💰 Energy savings: {savings_pct:.1f}%")
    else:
        print(f"\n  [Optimized] ❌ Simulation failed!")
    
    return success


def generate_report(data_logger: DataLogger):
    """Generate the final comparison report and dashboard data."""
    print("\n" + "="*70)
    print("  PHASE 3: GENERATING COMPARISON REPORT")
    print("="*70)
    
    # Export JSON report
    report_path = data_logger.export_report_json()
    
    # Export CSVs
    data_logger.export_csv("baseline")
    data_logger.export_csv("optimized")
    
    # Print summary
    report = data_logger.generate_comparison_report()
    summary = report["summary"]
    
    print(f"\n  {'='*50}")
    print(f"  📊 FINAL COMPARISON REPORT")
    print(f"  {'='*50}")
    print(f"  Baseline Energy:      {summary['baseline_energy_kwh']:>10.2f} kWh")
    print(f"  Optimized Energy:     {summary['optimized_energy_kwh']:>10.2f} kWh")
    print(f"  Energy Saved:         {summary['energy_savings_kwh']:>10.2f} kWh")
    print(f"  Savings Percentage:   {summary['energy_savings_percent']:>9.1f}%")
    print(f"  Est. Cost Savings:    ${summary['estimated_cost_savings_usd']:>9.2f}")
    print(f"  {'─'*50}")
    print(f"  Baseline Comfort Violations:  {summary['baseline_comfort_violations']}")
    print(f"  Optimized Comfort Violations: {summary['optimized_comfort_violations']}")
    print(f"  Agent Decisions Made:         {summary['total_agent_decisions']}")
    print(f"  Setpoint Changes:             {summary['total_setpoint_changes']}")
    print(f"  {'='*50}")
    
    # Copy report to dashboard directory
    dashboard_data = os.path.join(PROJECT_ROOT, "dashboard", "data.json")
    shutil.copy(report_path, dashboard_data)
    print(f"\n  Dashboard data saved to: {dashboard_data}")
    print(f"  Open dashboard/index.html in a browser to view results.")


def main():
    parser = argparse.ArgumentParser(description="Eco-Loop Building Agent System")
    parser.add_argument("--mode", choices=["full", "baseline", "optimized", "compare", "create-idf"],
                        default="full", help="Execution mode")
    parser.add_argument("--model", default="qwen2.5:7b",
                        help="Ollama model name (default: qwen2.5:7b)")
    parser.add_argument("--idf", default=IDF_FILE,
                        help="Path to IDF building model")
    parser.add_argument("--epw", default=EPW_FILE,
                        help="Path to EPW weather file")
    parser.add_argument("--ep-path", default=EP_PATH,
                        help="Path to EnergyPlus installation")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("  🏢 ECO-LOOP BUILDING AGENT SYSTEM")
    print("  Autonomous AI-Driven Building Energy Optimization")
    print("="*70)
    print(f"  Mode:    {args.mode}")
    print(f"  Model:   {args.model}")
    print(f"  IDF:     {args.idf}")
    print(f"  Weather: {args.epw}")
    print("="*70)
    
    # Create IDF if needed
    if args.mode == "create-idf" or not os.path.exists(args.idf):
        print("\n  Creating baseline building model...")
        create_baseline_office_idf(args.idf, args.epw)
        if args.mode == "create-idf":
            print("  Done!")
            return
    
    # Initialize data logger
    output_dir = os.path.join(PROJECT_ROOT, "output")
    data_logger = DataLogger(output_dir)
    
    if args.mode in ["full", "baseline"]:
        success = run_baseline_simulation(
            data_logger, args.ep_path, args.idf, args.epw
        )
        if not success and args.mode == "full":
            print("\n  ❌ Baseline simulation failed. Cannot continue.")
            sys.exit(1)
    
    if args.mode in ["full", "optimized"]:
        success = run_optimized_simulation(
            data_logger, args.model, args.ep_path, args.idf, args.epw
        )
        if not success:
            print("\n  ⚠️ Optimized simulation failed. Generating partial report.")
    
    if args.mode in ["full", "compare"]:
        # For compare mode, try to load existing data
        if args.mode == "compare":
            report_path = os.path.join(output_dir, "comparison_report.json")
            if os.path.exists(report_path):
                print("  Loading existing comparison data...")
            else:
                print("  ❌ No comparison data found. Run full mode first.")
                return
        generate_report(data_logger)
    
    print("\n  🎉 Eco-Loop execution complete!")


if __name__ == "__main__":
    main()
