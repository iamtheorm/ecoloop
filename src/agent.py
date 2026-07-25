"""
agent.py — LLM Agent orchestration for the Eco-Loop Building Control system.
Uses Ollama to run an open-source LLM with tool-calling capabilities.
"""

import json
import time
import traceback
from typing import Dict, Any, List, Optional, Callable
from src.agent_prompts import (
    SYSTEM_PROMPT, TOOL_DESCRIPTIONS, FEW_SHOT_EXAMPLES,
    build_sensor_summary_prompt
)
from src.mcp_server import execute_tool, set_sim_status
from src.data_logger import DataLogger


class EcoLoopAgent:
    """
    The AI brain of the Eco-Loop system. Uses an open-source LLM (via Ollama)
    to analyze building sensor data and make energy optimization decisions.
    """

    def __init__(self, model: str = "qwen2.5:7b", data_logger: DataLogger = None):
        """
        Initialize the agent.
        
        Args:
            model: Ollama model name (e.g., 'qwen2.5:7b', 'llama3.1:8b')
            data_logger: DataLogger instance for recording decisions
        """
        import ollama
        self.ollama = ollama
        self.model = model
        self.data_logger = data_logger
        
        # Conversation history (kept short for latency)
        self._messages: List[Dict[str, Any]] = []
        self._max_history = 10  # Keep last N exchanges to manage context length
        
        # Decision tracking
        self._decision_count = 0
        self._total_latency_ms = 0
        self._errors = 0
        
        # Initialize with system prompt
        self._reset_conversation()

    def _reset_conversation(self):
        """Reset the conversation with system prompt and few-shot examples."""
        self._messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        # Add few-shot examples
        for example in FEW_SHOT_EXAMPLES:
            self._messages.append(example)

    def _trim_history(self):
        """Keep conversation history manageable to control prompt latency."""
        # Always keep system prompt + few-shot examples
        base_count = 1 + len(FEW_SHOT_EXAMPLES)
        if len(self._messages) > base_count + self._max_history * 2:
            # Keep base + last N exchanges
            self._messages = (
                self._messages[:base_count] + 
                self._messages[-(self._max_history * 2):]
            )

    def analyze_and_act(self, sensor_data: Dict[str, Any], 
                        timestep: int) -> Dict[str, Any]:
        """
        Main agent loop: analyze sensor data and execute control actions.
        
        Args:
            sensor_data: Current sensor readings from EnergyPlus
            timestep: Current simulation timestep number
            
        Returns:
            Dict with agent's reasoning, actions taken, and performance metrics
        """
        start_time = time.time()
        
        # Build the simulation status
        sim_status = {
            "timestep": timestep,
            "hour": sensor_data.get("sim_hour", 0),
            "day": sensor_data.get("sim_day", 1),
            "month": sensor_data.get("sim_month", 1),
            "sim_time_hours": timestep * 0.25,  # 15-min intervals
        }
        set_sim_status(sim_status)
        
        # Build the prompt
        prompt = build_sensor_summary_prompt(sensor_data, sim_status)
        
        # Add to conversation
        self._messages.append({"role": "user", "content": prompt})
        self._trim_history()
        
        result = {
            "timestep": timestep,
            "reasoning": "",
            "actions": [],
            "errors": [],
            "latency_ms": 0,
        }
        
        try:
            # Call the LLM with tools
            response = self.ollama.chat(
                model=self.model,
                messages=self._messages,
                tools=TOOL_DESCRIPTIONS,
            )
            
            # Process the response
            assistant_msg = response.message
            
            # Check for tool calls
            if hasattr(assistant_msg, 'tool_calls') and assistant_msg.tool_calls:
                # Add assistant message to history
                self._messages.append({
                    "role": "assistant",
                    "content": assistant_msg.content or "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_msg.tool_calls
                    ]
                })
                
                # Execute each tool call
                for tool_call in assistant_msg.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = tool_call.function.arguments
                    
                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)
                    
                    print(f"  [Agent] Tool call: {tool_name}({tool_args})")
                    
                    # Execute the tool
                    tool_result = execute_tool(tool_name, tool_args)
                    
                    result["actions"].append({
                        "tool": tool_name,
                        "args": tool_args,
                        "result": json.loads(tool_result) if tool_result else {}
                    })
                    
                    # Add tool result to messages
                    self._messages.append({
                        "role": "tool",
                        "content": tool_result,
                    })
                
                # Get final response after tool execution
                try:
                    final_response = self.ollama.chat(
                        model=self.model,
                        messages=self._messages,
                    )
                    result["reasoning"] = final_response.message.content or ""
                    self._messages.append({
                        "role": "assistant",
                        "content": result["reasoning"]
                    })
                except Exception as e:
                    result["reasoning"] = assistant_msg.content or "Actions executed."
            else:
                # No tool calls, just reasoning
                result["reasoning"] = assistant_msg.content or ""
                self._messages.append({
                    "role": "assistant",
                    "content": result["reasoning"]
                })
        
        except Exception as e:
            error_msg = f"Agent error: {str(e)}"
            print(f"  [Agent] ERROR: {error_msg}")
            traceback.print_exc()
            result["errors"].append(error_msg)
            self._errors += 1
            
            # Fallback: apply rule-based control
            fallback_actions = self._fallback_control(sensor_data, sim_status)
            result["actions"] = fallback_actions
            result["reasoning"] = f"Fallback rule-based control applied due to error: {error_msg}"
        
        # Record metrics
        elapsed_ms = int((time.time() - start_time) * 1000)
        result["latency_ms"] = elapsed_ms
        self._decision_count += 1
        self._total_latency_ms += elapsed_ms
        
        # Log the decision
        if self.data_logger:
            self.data_logger.log_agent_decision(
                timestep=timestep,
                sim_time_hours=sim_status.get("sim_time_hours", 0),
                reasoning=result["reasoning"][:500],  # Truncate for storage
                actions=result["actions"],
                sensor_summary={
                    "zones": {z: {"temp": d.get("temp_c"), "pmv": d.get("pmv")}
                              for z, d in sensor_data.get("zones", {}).items()},
                    "outdoor_temp": sensor_data.get("outdoor", {}).get("temp_c"),
                    "total_power_w": sensor_data.get("energy", {}).get("total_w"),
                }
            )
        
        # Print summary
        action_count = len(result["actions"])
        print(f"  [Agent] Decision #{self._decision_count}: "
              f"{action_count} actions, {elapsed_ms}ms latency")
        
        return result

    def _fallback_control(self, sensor_data: Dict[str, Any], 
                          sim_status: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Rule-based fallback control when LLM is unavailable or errors out.
        Implements basic energy-saving strategies.
        """
        actions = []
        hour = sim_status.get("hour", 12)
        is_occupied = 8 <= hour <= 18
        is_peak = 14 <= hour <= 17
        
        zones = sensor_data.get("zones", {})
        outdoor_temp = sensor_data.get("outdoor", {}).get("temp_c", 25)
        
        for zone_name, zone_data in zones.items():
            occupancy = zone_data.get("occupancy", 0)
            temp = zone_data.get("temp_c", 22)
            
            if not is_occupied or occupancy == 0:
                # Unoccupied: wide dead band
                heating_sp = 16.0
                cooling_sp = 28.0
                lighting = 0.1
            elif is_peak:
                # Peak demand: slightly wider dead band
                heating_sp = 20.0
                cooling_sp = 25.0
                lighting = 0.8
            else:
                # Normal occupied: standard comfort
                heating_sp = 21.0
                cooling_sp = 24.0
                lighting = 1.0
            
            # Server room always needs cooling
            if zone_name == "ServerRoom":
                cooling_sp = min(cooling_sp, 24.0)
                heating_sp = 18.0
            
            # Apply changes
            execute_tool("set_heating_setpoint", {
                "zone_name": zone_name, "temperature": heating_sp
            })
            execute_tool("set_cooling_setpoint", {
                "zone_name": zone_name, "temperature": cooling_sp
            })
            execute_tool("set_lighting_fraction", {
                "zone_name": zone_name, "fraction": lighting
            })
            
            actions.append({
                "tool": "fallback_control",
                "args": {
                    "zone": zone_name,
                    "heating_sp": heating_sp,
                    "cooling_sp": cooling_sp,
                    "lighting": lighting,
                },
                "result": {"success": True}
            })
        
        return actions

    @property
    def avg_latency_ms(self) -> float:
        if self._decision_count == 0:
            return 0
        return round(self._total_latency_ms / self._decision_count, 1)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_decisions": self._decision_count,
            "total_errors": self._errors,
            "avg_latency_ms": self.avg_latency_ms,
            "model": self.model,
        }
