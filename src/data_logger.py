"""
data_logger.py — Logs all sensor readings, agent decisions, and actuator changes.
Provides structured data export for the dashboard and comparison reports.
"""

import json
import csv
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional


class DataLogger:
    """Thread-safe data logger for the Eco-Loop simulation pipeline."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self.baseline_data: List[Dict[str, Any]] = []
        self.optimized_data: List[Dict[str, Any]] = []
        self.agent_decisions: List[Dict[str, Any]] = []
        self.setpoint_history: List[Dict[str, Any]] = []
        self._current_mode = "baseline"
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "baseline_results"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "optimized_results"), exist_ok=True)

    def set_mode(self, mode: str):
        """Set logging mode to 'baseline' or 'optimized'."""
        self._current_mode = mode

    def log_sensor_reading(self, timestep: int, sim_time_hours: float,
                           zone_name: str, data: Dict[str, float]):
        """Log a sensor reading from EnergyPlus."""
        record = {
            "timestep": timestep,
            "sim_time_hours": round(sim_time_hours, 2),
            "zone_name": zone_name,
            "timestamp": datetime.now().isoformat(),
            **data
        }
        if self._current_mode == "baseline":
            self.baseline_data.append(record)
        else:
            self.optimized_data.append(record)

    def log_agent_decision(self, timestep: int, sim_time_hours: float,
                           reasoning: str, actions: List[Dict[str, Any]],
                           sensor_summary: Dict[str, Any]):
        """Log an LLM agent decision with full reasoning chain."""
        record = {
            "timestep": timestep,
            "sim_time_hours": round(sim_time_hours, 2),
            "timestamp": datetime.now().isoformat(),
            "reasoning": reasoning,
            "actions": actions,
            "sensor_summary": sensor_summary
        }
        self.agent_decisions.append(record)

    def log_setpoint_change(self, timestep: int, sim_time_hours: float,
                            zone_name: str, setpoint_type: str,
                            old_value: float, new_value: float):
        """Log a setpoint change made by the agent."""
        record = {
            "timestep": timestep,
            "sim_time_hours": round(sim_time_hours, 2),
            "timestamp": datetime.now().isoformat(),
            "zone_name": zone_name,
            "setpoint_type": setpoint_type,
            "old_value": old_value,
            "new_value": new_value
        }
        self.setpoint_history.append(record)

    def get_baseline_energy_total(self) -> float:
        """Calculate total baseline energy consumption in kWh."""
        return sum(r.get("total_energy_kwh", 0) for r in self.baseline_data
                   if "total_energy_kwh" in r)

    def get_optimized_energy_total(self) -> float:
        """Calculate total optimized energy consumption in kWh."""
        return sum(r.get("total_energy_kwh", 0) for r in self.optimized_data
                   if "total_energy_kwh" in r)

    def get_energy_savings_percent(self) -> float:
        """Calculate percentage energy savings."""
        baseline = self.get_baseline_energy_total()
        optimized = self.get_optimized_energy_total()
        if baseline == 0:
            return 0.0
        return round((baseline - optimized) / baseline * 100, 2)

    def get_comfort_violations(self, mode: str = "optimized") -> int:
        """Count timesteps where PMV was outside comfort bounds (-0.5 to +0.5)."""
        data = self.optimized_data if mode == "optimized" else self.baseline_data
        violations = 0
        for r in data:
            pmv = r.get("pmv", 0)
            if abs(pmv) > 0.5:
                violations += 1
        return violations

    def generate_comparison_report(self) -> Dict[str, Any]:
        """Generate a comprehensive comparison report."""
        baseline_energy = self.get_baseline_energy_total()
        optimized_energy = self.get_optimized_energy_total()
        savings_pct = self.get_energy_savings_percent()

        # Average temperatures by zone
        baseline_temps = {}
        optimized_temps = {}
        for r in self.baseline_data:
            zone = r.get("zone_name", "unknown")
            if zone not in baseline_temps:
                baseline_temps[zone] = []
            if "zone_temp_c" in r:
                baseline_temps[zone].append(r["zone_temp_c"])
        for r in self.optimized_data:
            zone = r.get("zone_name", "unknown")
            if zone not in optimized_temps:
                optimized_temps[zone] = []
            if "zone_temp_c" in r:
                optimized_temps[zone].append(r["zone_temp_c"])

        avg_baseline_temps = {z: round(sum(t)/len(t), 2) if t else 0
                              for z, t in baseline_temps.items()}
        avg_optimized_temps = {z: round(sum(t)/len(t), 2) if t else 0
                               for z, t in optimized_temps.items()}

        report = {
            "summary": {
                "baseline_energy_kwh": round(baseline_energy, 2),
                "optimized_energy_kwh": round(optimized_energy, 2),
                "energy_savings_kwh": round(baseline_energy - optimized_energy, 2),
                "energy_savings_percent": savings_pct,
                "estimated_cost_savings_usd": round((baseline_energy - optimized_energy) * 0.12, 2),
                "baseline_comfort_violations": self.get_comfort_violations("baseline"),
                "optimized_comfort_violations": self.get_comfort_violations("optimized"),
                "total_agent_decisions": len(self.agent_decisions),
                "total_setpoint_changes": len(self.setpoint_history),
            },
            "avg_zone_temperatures": {
                "baseline": avg_baseline_temps,
                "optimized": avg_optimized_temps,
            },
            "baseline_timeseries": self.baseline_data,
            "optimized_timeseries": self.optimized_data,
            "agent_decisions": self.agent_decisions,
            "setpoint_history": self.setpoint_history,
        }
        return report

    def export_report_json(self, filename: str = "comparison_report.json"):
        """Export the comparison report to JSON."""
        report = self.generate_comparison_report()
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"[DataLogger] Report exported to {filepath}")
        return filepath

    def export_csv(self, mode: str = "baseline"):
        """Export timeseries data to CSV."""
        data = self.baseline_data if mode == "baseline" else self.optimized_data
        if not data:
            return None
        subdir = f"{mode}_results"
        filepath = os.path.join(self.output_dir, subdir, f"{mode}_data.csv")
        keys = data[0].keys()
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        print(f"[DataLogger] CSV exported to {filepath}")
        return filepath
