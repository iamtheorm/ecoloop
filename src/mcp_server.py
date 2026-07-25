"""
mcp_server.py — Model Context Protocol server exposing EnergyPlus tools.
Built with FastMCP from the mcp Python SDK.
Provides tools for reading sensors, setting actuators, and managing simulations.
"""

import json
import sys
import os
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("EcoLoop Building Agent Server")

# Shared state — set by the main orchestrator before starting the server
_ep_wrapper = None
_data_logger = None
_sim_status = {}


def set_ep_wrapper(wrapper):
    """Set the EnergyPlus wrapper instance."""
    global _ep_wrapper
    _ep_wrapper = wrapper


def set_data_logger(logger):
    """Set the data logger instance."""
    global _data_logger
    _data_logger = logger


def set_sim_status(status: dict):
    """Update the current simulation status."""
    global _sim_status
    _sim_status = status


def _get_sensor_data():
    """Get the latest sensor data from EnergyPlus."""
    if _ep_wrapper:
        return _ep_wrapper.get_latest_sensor_data()
    return {}


# ===== MCP TOOLS =====

@mcp.tool()
def read_zone_sensors(zone_name: str) -> str:
    """Read current temperature, humidity, occupancy count, and PMV comfort index for a specific thermal zone.
    
    Args:
        zone_name: Name of the thermal zone (e.g., 'OpenOffice', 'ConferenceRoom', 'ServerRoom')
    
    Returns:
        JSON string with zone sensor data
    """
    data = _get_sensor_data()
    zones = data.get("zones", {})
    
    if zone_name in zones:
        result = {
            "zone_name": zone_name,
            "temperature_c": zones[zone_name].get("temp_c", "N/A"),
            "humidity_ratio": zones[zone_name].get("humidity_ratio", "N/A"),
            "occupancy": zones[zone_name].get("occupancy", 0),
            "pmv": zones[zone_name].get("pmv", "N/A"),
            "heating_setpoint_c": zones[zone_name].get("heating_sp", "N/A"),
            "cooling_setpoint_c": zones[zone_name].get("cooling_sp", "N/A"),
        }
    else:
        available = list(zones.keys())
        result = {"error": f"Zone '{zone_name}' not found. Available zones: {available}"}
    
    return json.dumps(result, indent=2)


@mcp.tool()
def read_energy_consumption() -> str:
    """Get current energy consumption data including total facility power, HVAC power, and lighting power in Watts.
    Also includes cumulative energy in kWh.
    
    Returns:
        JSON string with energy consumption data
    """
    data = _get_sensor_data()
    energy = data.get("energy", {})
    
    result = {
        "total_facility_w": energy.get("total_w", 0),
        "hvac_w": energy.get("hvac_w", 0),
        "lighting_w": energy.get("lighting_w", 0),
        "cumulative_kwh": energy.get("cumulative_kwh", 0),
        "timestep_kwh": energy.get("total_energy_kwh", 0),
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
def read_outdoor_conditions() -> str:
    """Get current outdoor weather conditions including temperature, humidity, wind speed, and solar radiation.
    
    Returns:
        JSON string with outdoor conditions
    """
    data = _get_sensor_data()
    outdoor = data.get("outdoor", {})
    
    result = {
        "temperature_c": outdoor.get("temp_c", "N/A"),
        "relative_humidity_pct": outdoor.get("humidity_pct", "N/A"),
        "wind_speed_ms": outdoor.get("wind_speed_ms", "N/A"),
        "solar_radiation_wm2": outdoor.get("solar_w_m2", "N/A"),
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
def read_pmv_comfort(zone_name: str) -> str:
    """Get the Predicted Mean Vote (PMV) thermal comfort index for a specific zone.
    PMV ranges from -3 (cold) to +3 (hot). The comfort zone is -0.5 to +0.5.
    
    Args:
        zone_name: Name of the thermal zone
    
    Returns:
        JSON string with PMV data and comfort assessment
    """
    data = _get_sensor_data()
    zones = data.get("zones", {})
    
    if zone_name in zones:
        pmv = zones[zone_name].get("pmv", 0)
        temp = zones[zone_name].get("temp_c", 22)
        
        if pmv < -0.5:
            comfort_status = "TOO COLD - increase heating"
        elif pmv > 0.5:
            comfort_status = "TOO WARM - increase cooling"
        else:
            comfort_status = "COMFORTABLE"
        
        result = {
            "zone_name": zone_name,
            "pmv": pmv,
            "temperature_c": temp,
            "comfort_status": comfort_status,
            "acceptable_range": "-0.5 to +0.5",
        }
    else:
        result = {"error": f"Zone '{zone_name}' not found"}
    
    return json.dumps(result, indent=2)


@mcp.tool()
def set_cooling_setpoint(zone_name: str, temperature: float) -> str:
    """Override the cooling setpoint temperature for a specific zone.
    Must be between 23°C and 28°C. Values above 26°C should only be used during unoccupied hours.
    
    Args:
        zone_name: Name of the thermal zone
        temperature: New cooling setpoint in °C (23-28 range)
    
    Returns:
        JSON string confirming the change
    """
    if temperature < 20 or temperature > 32:
        return json.dumps({"error": f"Temperature {temperature}°C out of safe range (20-32°C)"})
    
    key = f"{zone_name}_cooling_sp"
    old_value = 24.0
    
    if _ep_wrapper:
        old_data = _ep_wrapper.get_latest_sensor_data()
        old_value = old_data.get("zones", {}).get(zone_name, {}).get("cooling_sp", 24.0)
        _ep_wrapper.set_actuator(key, temperature)
    
    if _data_logger:
        _data_logger.log_setpoint_change(
            _sim_status.get("timestep", 0),
            _sim_status.get("sim_time_hours", 0),
            zone_name, "cooling", old_value, temperature
        )
    
    return json.dumps({
        "success": True,
        "zone_name": zone_name,
        "setpoint_type": "cooling",
        "old_value_c": old_value,
        "new_value_c": temperature,
    }, indent=2)


@mcp.tool()
def set_heating_setpoint(zone_name: str, temperature: float) -> str:
    """Override the heating setpoint temperature for a specific zone.
    Must be between 16°C and 23°C. Values below 19°C should only be used during unoccupied hours.
    
    Args:
        zone_name: Name of the thermal zone
        temperature: New heating setpoint in °C (16-23 range)
    
    Returns:
        JSON string confirming the change
    """
    if temperature < 10 or temperature > 26:
        return json.dumps({"error": f"Temperature {temperature}°C out of safe range (10-26°C)"})
    
    key = f"{zone_name}_heating_sp"
    old_value = 21.0
    
    if _ep_wrapper:
        old_data = _ep_wrapper.get_latest_sensor_data()
        old_value = old_data.get("zones", {}).get(zone_name, {}).get("heating_sp", 21.0)
        _ep_wrapper.set_actuator(key, temperature)
    
    if _data_logger:
        _data_logger.log_setpoint_change(
            _sim_status.get("timestep", 0),
            _sim_status.get("sim_time_hours", 0),
            zone_name, "heating", old_value, temperature
        )
    
    return json.dumps({
        "success": True,
        "zone_name": zone_name,
        "setpoint_type": "heating",
        "old_value_c": old_value,
        "new_value_c": temperature,
    }, indent=2)


@mcp.tool()
def set_lighting_fraction(zone_name: str, fraction: float) -> str:
    """Override the lighting power fraction for a zone.
    1.0 = full power, 0.0 = off. Use lower values for unoccupied zones.
    
    Args:
        zone_name: Name of the thermal zone
        fraction: Lighting power fraction (0.0 to 1.0)
    
    Returns:
        JSON string confirming the change
    """
    fraction = max(0.0, min(1.0, fraction))
    
    key = f"{zone_name}_lighting"
    if _ep_wrapper:
        _ep_wrapper.set_actuator(key, fraction)
    
    return json.dumps({
        "success": True,
        "zone_name": zone_name,
        "lighting_fraction": fraction,
    }, indent=2)


@mcp.tool()
def get_simulation_status() -> str:
    """Get overall simulation status including current time, occupancy status, 
    total energy consumed, and whether it's a peak demand period.
    
    Returns:
        JSON string with simulation status
    """
    data = _get_sensor_data()
    hour = data.get("sim_hour", 0)
    day = data.get("sim_day", 1)
    month = data.get("sim_month", 1)
    
    is_occupied = 8 <= hour <= 18
    is_peak = 14 <= hour <= 17
    is_weekday = True  # Simplified
    
    energy = data.get("energy", {})
    
    result = {
        "hour": hour,
        "day": day,
        "month": month,
        "timestep": data.get("timestep", 0),
        "is_occupied": is_occupied,
        "is_peak_demand": is_peak,
        "is_weekday": is_weekday,
        "cumulative_energy_kwh": energy.get("cumulative_kwh", 0),
        "current_total_power_w": energy.get("total_w", 0),
    }
    
    return json.dumps(result, indent=2)


@mcp.tool()
def compare_with_baseline() -> str:
    """Compare current AI-controlled energy consumption against the baseline.
    Shows percentage savings and comfort metrics.
    
    Returns:
        JSON string with comparison data
    """
    if _data_logger:
        baseline = _data_logger.get_baseline_energy_total()
        optimized = _data_logger.get_optimized_energy_total()
        savings_pct = _data_logger.get_energy_savings_percent()
        
        result = {
            "baseline_kwh": round(baseline, 2),
            "optimized_kwh": round(optimized, 2),
            "savings_kwh": round(baseline - optimized, 2),
            "savings_percent": savings_pct,
            "baseline_comfort_violations": _data_logger.get_comfort_violations("baseline"),
            "optimized_comfort_violations": _data_logger.get_comfort_violations("optimized"),
        }
    else:
        result = {"error": "Data logger not available"}
    
    return json.dumps(result, indent=2)


# Direct tool execution functions (used by agent without MCP protocol)
TOOL_FUNCTIONS = {
    "read_zone_sensors": read_zone_sensors,
    "read_energy_consumption": read_energy_consumption,
    "read_outdoor_conditions": read_outdoor_conditions,
    "read_pmv_comfort": read_pmv_comfort,
    "set_cooling_setpoint": set_cooling_setpoint,
    "set_heating_setpoint": set_heating_setpoint,
    "set_lighting_fraction": set_lighting_fraction,
    "get_simulation_status": get_simulation_status,
    "compare_with_baseline": compare_with_baseline,
}


def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments."""
    if tool_name in TOOL_FUNCTIONS:
        func = TOOL_FUNCTIONS[tool_name]
        try:
            # Call the underlying function directly (unwrapped from @mcp.tool)
            return func(**arguments)
        except Exception as e:
            return json.dumps({"error": f"Tool execution failed: {str(e)}"})
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}. Available: {list(TOOL_FUNCTIONS.keys())}"})


if __name__ == "__main__":
    # Run as standalone MCP server (stdio transport)
    mcp.run(transport="stdio")
