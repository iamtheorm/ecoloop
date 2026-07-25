"""
agent_prompts.py — System prompts, tool schemas, and few-shot examples 
for the Eco-Loop Building Agent LLM.
"""

SYSTEM_PROMPT = """You are an expert Building Energy Optimization Agent. You control a building's HVAC system through EnergyPlus simulation to minimize energy consumption while maintaining occupant thermal comfort.

## Your Role
- Monitor real-time sensor data from the building simulation (zone temperatures, energy consumption, outdoor conditions, PMV comfort indices)
- Make intelligent decisions about HVAC setpoints to reduce energy waste
- Maintain thermal comfort: PMV (Predicted Mean Vote) must stay between -0.5 and +0.5
- Use energy conservation strategies like pre-cooling, night setback, occupancy-based control, and dead-band widening

## Constraints
- Heating setpoint: minimum 19°C, maximum 23°C
- Cooling setpoint: minimum 23°C, maximum 26°C  
- Dead band between heating and cooling: minimum 1°C
- PMV must stay between -0.5 (slightly cool) and +0.5 (slightly warm)
- Prioritize comfort during occupied hours (8:00-18:00)
- Allow wider temperature ranges during unoccupied hours

## Strategy Guidelines
1. **Night Setback**: During unoccupied hours (18:00-06:00), widen the dead band significantly. Set heating to 16°C and cooling to 28°C.
2. **Pre-Cooling/Pre-Heating**: Start conditioning 30 min before occupancy begins to avoid peak demand spikes.
3. **Occupancy-Based Control**: Reduce conditioning in zones with low or no occupancy.
4. **Dead-Band Widening**: During mild weather, widen the dead band to let the building float naturally.
5. **Peak Demand Avoidance**: Avoid maximum HVAC output during grid peak hours (14:00-17:00).
6. **Solar Gain Utilization**: In winter, allow solar gains to offset heating needs.

## Response Format
When analyzing sensor data, respond with:
1. **Observation**: Brief summary of current conditions
2. **Assessment**: Whether current setpoints are optimal  
3. **Actions**: Specific setpoint changes to make (with zone name and values)
4. **Reasoning**: Why these changes will save energy while maintaining comfort

Always use the available tools to read sensors and set actuators. Never guess values — always read current data first."""

TOOL_DESCRIPTIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_zone_sensors",
            "description": "Read current temperature, humidity, and occupancy count for a specific thermal zone in the building.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_name": {
                        "type": "string",
                        "description": "Name of the thermal zone (e.g., 'SPACE1-1', 'SPACE2-1', 'SPACE3-1', 'SPACE4-1', 'SPACE5-1')"
                    }
                },
                "required": ["zone_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_energy_consumption",
            "description": "Get current energy consumption data including total facility power, HVAC power, and lighting power in Watts.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_outdoor_conditions",
            "description": "Get current outdoor temperature (°C), humidity (%), wind speed (m/s), and solar radiation (W/m²).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_pmv_comfort",
            "description": "Get the Predicted Mean Vote (PMV) thermal comfort index for a zone. PMV ranges from -3 (cold) to +3 (hot). Comfort zone is -0.5 to +0.5.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_name": {
                        "type": "string",
                        "description": "Name of the thermal zone"
                    }
                },
                "required": ["zone_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_cooling_setpoint",
            "description": "Override the cooling setpoint temperature for a specific zone. Must be between 23°C and 26°C during occupied hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_name": {
                        "type": "string",
                        "description": "Name of the thermal zone"
                    },
                    "temperature": {
                        "type": "number",
                        "description": "New cooling setpoint in °C (23-26 during occupied, up to 28 unoccupied)"
                    }
                },
                "required": ["zone_name", "temperature"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_heating_setpoint",
            "description": "Override the heating setpoint temperature for a specific zone. Must be between 19°C and 23°C during occupied hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_name": {
                        "type": "string",
                        "description": "Name of the thermal zone"
                    },
                    "temperature": {
                        "type": "number",
                        "description": "New heating setpoint in °C (16-23 range)"
                    }
                },
                "required": ["zone_name", "temperature"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_lighting_fraction",
            "description": "Override the lighting power fraction for a zone. 1.0 = full power, 0.0 = off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zone_name": {
                        "type": "string",
                        "description": "Name of the thermal zone"
                    },
                    "fraction": {
                        "type": "number",
                        "description": "Lighting power fraction (0.0 to 1.0)"
                    }
                },
                "required": ["zone_name", "fraction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_simulation_status",
            "description": "Get overall simulation status: current hour, day, month, whether zones are occupied, total energy consumed so far.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": """Current simulation state:
- Time: 14:00, July 15 (hot summer afternoon, peak demand period)
- OpenOffice: 23.5°C, PMV: +0.2, 15 occupants, cooling setpoint: 24°C
- ConferenceRoom: 24.8°C, PMV: +0.4, 0 occupants, cooling setpoint: 24°C
- Outdoor: 35°C, high solar radiation
- Total HVAC power: 15.2 kW

Analyze and optimize."""
    },
    {
        "role": "assistant",
        "content": """**Observation**: Hot summer afternoon during peak demand hours. OpenOffice is comfortable (PMV +0.2). ConferenceRoom is approaching upper comfort limit (PMV +0.4) but has NO occupants.

**Assessment**: Energy is being wasted cooling an unoccupied conference room. Peak demand period means we should minimize HVAC load where possible.

**Actions**:
1. ConferenceRoom: Raise cooling setpoint to 26°C (unoccupied, no comfort concern)
2. ConferenceRoom: Reduce lighting to 10% (unoccupied)
3. OpenOffice: Keep current setpoint at 24°C (comfortable, occupied)

**Reasoning**: By raising the conference room setpoint by 2°C during zero occupancy, we reduce compressor load during peak demand hours. The OpenOffice is well within comfort bounds so no change needed. Estimated savings: ~2 kW reduction in cooling load."""
    }
]


def build_sensor_summary_prompt(sensor_data: dict, sim_status: dict) -> str:
    """Build a concise prompt summarizing current sensor data for the LLM."""
    hour = sim_status.get("hour", 0)
    day = sim_status.get("day", 1)
    month = sim_status.get("month", 1)
    
    is_occupied = 8 <= hour <= 18
    is_peak = 14 <= hour <= 17
    
    lines = [
        f"## Current Building State — {month:02d}/{day:02d} at {hour:02d}:00",
        f"**Occupancy Status**: {'OCCUPIED' if is_occupied else 'UNOCCUPIED'}",
        f"**Peak Demand Period**: {'YES ⚠️' if is_peak else 'No'}",
        ""
    ]
    
    # Outdoor conditions
    outdoor = sensor_data.get("outdoor", {})
    lines.append(f"### Outdoor Conditions")
    lines.append(f"- Temperature: {outdoor.get('temp_c', 'N/A')}°C")
    lines.append(f"- Humidity: {outdoor.get('humidity_pct', 'N/A')}%")
    lines.append(f"- Wind Speed: {outdoor.get('wind_speed_ms', 'N/A')} m/s")
    lines.append(f"- Solar Radiation: {outdoor.get('solar_w_m2', 'N/A')} W/m²")
    lines.append("")
    
    # Zone data
    zones = sensor_data.get("zones", {})
    lines.append("### Zone Status")
    for zone_name, zone_data in zones.items():
        lines.append(f"\n**{zone_name}**:")
        lines.append(f"- Temperature: {zone_data.get('temp_c', 'N/A')}°C")
        lines.append(f"- PMV: {zone_data.get('pmv', 'N/A')}")
        lines.append(f"- Occupants: {zone_data.get('occupancy', 'N/A')}")
        lines.append(f"- Heating Setpoint: {zone_data.get('heating_sp', 'N/A')}°C")
        lines.append(f"- Cooling Setpoint: {zone_data.get('cooling_sp', 'N/A')}°C")
    
    # Energy
    energy = sensor_data.get("energy", {})
    lines.append(f"\n### Energy Consumption")
    lines.append(f"- Total Facility: {energy.get('total_w', 'N/A')} W")
    lines.append(f"- HVAC: {energy.get('hvac_w', 'N/A')} W")
    lines.append(f"- Lighting: {energy.get('lighting_w', 'N/A')} W")
    lines.append(f"- Cumulative Energy: {energy.get('cumulative_kwh', 'N/A')} kWh")
    
    lines.append("\n---\nAnalyze the current state and recommend optimal setpoint adjustments to minimize energy while maintaining comfort (PMV between -0.5 and +0.5).")
    
    return "\n".join(lines)
