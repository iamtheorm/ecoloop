"""
energyplus_wrapper.py — Manages the EnergyPlus simulation lifecycle using the Python API.
Handles sensor reading, actuator control, and real-time data streaming.
"""

import sys
import os
import threading
import time
from queue import Queue, Empty
from typing import Dict, Any, Optional, Callable, List
import json


class EnergyPlusWrapper:
    """
    Wraps the EnergyPlus Python API (pyenergyplus) for real-time simulation
    control with sensor reading and actuator writing via callbacks.
    """

    def __init__(self, energyplus_path: str = None):
        """
        Initialize the EnergyPlus wrapper.
        
        Args:
            energyplus_path: Path to the EnergyPlus installation directory.
                             If None, tries to auto-detect.
        """
        self.ep_path = energyplus_path or self._find_energyplus()
        self._setup_python_path()
        
        from pyenergyplus.api import EnergyPlusAPI
        self.api = EnergyPlusAPI()
        self.state = None
        
        # Handles (initialized lazily during simulation)
        self._sensor_handles: Dict[str, int] = {}
        self._actuator_handles: Dict[str, int] = {}
        self._handles_initialized = False
        
        # Data buffers (thread-safe)
        self._sensor_data: Dict[str, Any] = {}
        self._data_lock = threading.Lock()
        self._data_queue = Queue(maxsize=1000)
        
        # Control state
        self._actuator_values: Dict[str, float] = {}
        self._actuator_lock = threading.Lock()
        
        # Simulation state
        self._timestep_count = 0
        self._sim_running = False
        self._warmup_complete = False
        self._cumulative_energy_j = 0.0
        
        # Callback hook for external consumers (e.g., the agent)
        self._on_timestep_callback: Optional[Callable] = None
        
        # Zone names (populated after IDF parsing)
        self.zone_names: List[str] = []

    def _find_energyplus(self) -> str:
        """Auto-detect EnergyPlus installation path."""
        possible_paths = [
            "/usr/local/EnergyPlus-24-1-0",
            "/Applications/EnergyPlus-24-1-0",
            os.path.expanduser("~/EnergyPlus-24-1-0"),
            os.path.expanduser("~/EnergyPlus"),
            # Common Linux paths
            "/usr/local/bin",
        ]
        # Also check if there's an extracted tarball in the project
        project_ep = os.path.join(os.path.dirname(os.path.dirname(__file__)), "energyplus")
        possible_paths.insert(0, project_ep)
        
        for path in possible_paths:
            if os.path.exists(path):
                # Check for the API module
                pyep = os.path.join(path, "pyenergyplus")
                if os.path.exists(pyep):
                    return path
        
        # Last resort: check PATH
        import shutil
        ep_bin = shutil.which("energyplus")
        if ep_bin:
            return os.path.dirname(ep_bin)
        
        raise FileNotFoundError(
            "EnergyPlus installation not found. Please set energyplus_path "
            "or install EnergyPlus and ensure it's in your PATH."
        )

    def _setup_python_path(self):
        """Add EnergyPlus to Python path so pyenergyplus can be imported."""
        if self.ep_path not in sys.path:
            sys.path.insert(0, self.ep_path)

    def set_zone_names(self, zones: List[str]):
        """Set the zone names to monitor."""
        self.zone_names = zones

    def set_on_timestep_callback(self, callback: Callable):
        """Register a callback to be called after each timestep."""
        self._on_timestep_callback = callback

    def _init_handles(self, state):
        """Initialize sensor and actuator handles. Called once when data is ready."""
        if self._handles_initialized:
            return
        
        if not self.api.exchange.api_data_fully_ready(state):
            return
        
        print("[EP] Initializing sensor and actuator handles...")
        
        for zone in self.zone_names:
            # Zone temperature sensor
            h = self.api.exchange.get_variable_handle(
                state, "Zone Mean Air Temperature", zone
            )
            if h >= 0:
                self._sensor_handles[f"{zone}_temp"] = h
            
            # Zone humidity
            h = self.api.exchange.get_variable_handle(
                state, "Zone Mean Air Humidity Ratio", zone
            )
            if h >= 0:
                self._sensor_handles[f"{zone}_humidity"] = h
            
            # Zone occupancy
            h = self.api.exchange.get_variable_handle(
                state, "Zone People Occupant Count", zone
            )
            if h >= 0:
                self._sensor_handles[f"{zone}_occupancy"] = h
            
            # Heating setpoint actuator
            h = self.api.exchange.get_actuator_handle(
                state,
                "Zone Temperature Control",
                "Heating Setpoint",
                zone
            )
            if h >= 0:
                self._actuator_handles[f"{zone}_heating_sp"] = h
            
            # Cooling setpoint actuator
            h = self.api.exchange.get_actuator_handle(
                state,
                "Zone Temperature Control",
                "Cooling Setpoint",
                zone
            )
            if h >= 0:
                self._actuator_handles[f"{zone}_cooling_sp"] = h
            
            # Lighting schedule actuator
            h = self.api.exchange.get_actuator_handle(
                state,
                "Schedule:Compact",
                "Schedule Value",
                "LIGHTS-1"
            )
            if h >= 0:
                self._actuator_handles[f"{zone}_lighting"] = h
        
        # Outdoor sensors
        h = self.api.exchange.get_variable_handle(
            state, "Site Outdoor Air Drybulb Temperature", "Environment"
        )
        if h >= 0:
            self._sensor_handles["outdoor_temp"] = h
        
        h = self.api.exchange.get_variable_handle(
            state, "Site Outdoor Air Relative Humidity", "Environment"
        )
        if h >= 0:
            self._sensor_handles["outdoor_humidity"] = h
        
        h = self.api.exchange.get_variable_handle(
            state, "Site Wind Speed", "Environment"
        )
        if h >= 0:
            self._sensor_handles["outdoor_wind"] = h
        
        h = self.api.exchange.get_variable_handle(
            state, "Site Direct Solar Radiation Rate per Area", "Environment"
        )
        if h >= 0:
            self._sensor_handles["outdoor_solar"] = h
        
        # Facility energy meters (using variables instead of meters for reliable API access)
        h = self.api.exchange.get_variable_handle(state, "Facility Total Building Electricity Demand Rate", "Whole Building")
        if h >= 0:
            self._sensor_handles["facility_energy"] = h
        
        h = self.api.exchange.get_variable_handle(state, "Facility Total HVAC Electricity Demand Rate", "Whole Building")
        if h >= 0:
            self._sensor_handles["hvac_energy"] = h
        
        h = self.api.exchange.get_meter_handle(state, "InteriorLights:Electricity")
        if h >= 0:
            self._sensor_handles["lighting_energy"] = h
        
        self._handles_initialized = True
        print(f"[EP] Initialized {len(self._sensor_handles)} sensors, "
              f"{len(self._actuator_handles)} actuators")

    def _timestep_callback(self, state):
        """Called at the end of each zone timestep."""
        # Skip warmup
        if self.api.exchange.warmup_flag(state):
            return
        
        self._warmup_complete = True
        self._init_handles(state)
        
        if not self._handles_initialized:
            return
        
        self._timestep_count += 1
        
        # Read all sensor values
        sensor_data = self._read_all_sensors(state)
        
        # Apply any pending actuator overrides
        self._apply_actuator_values(state)
        
        # Store data
        with self._data_lock:
            self._sensor_data = sensor_data
        
        # Push to queue for external consumers
        try:
            self._data_queue.put_nowait(sensor_data)
        except:
            pass  # Queue full, skip
        
        # Call external callback
        if self._on_timestep_callback and self._timestep_count % 1 == 0:
            try:
                self._on_timestep_callback(sensor_data, self._timestep_count)
            except Exception as e:
                print(f"[EP] Callback error: {e}")

    def _read_all_sensors(self, state) -> Dict[str, Any]:
        """Read all registered sensor values."""
        data = {
            "timestep": self._timestep_count,
            "sim_hour": self.api.exchange.hour(state),
            "sim_day": self.api.exchange.day_of_month(state),
            "sim_month": self.api.exchange.month(state),
            "zones": {},
            "outdoor": {},
            "energy": {},
        }
        
        # Zone data
        for zone in self.zone_names:
            zone_data = {}
            
            key = f"{zone}_temp"
            if key in self._sensor_handles:
                zone_data["temp_c"] = round(
                    self.api.exchange.get_variable_value(state, self._sensor_handles[key]), 2
                )
            
            key = f"{zone}_humidity"
            if key in self._sensor_handles:
                zone_data["humidity_ratio"] = round(
                    self.api.exchange.get_variable_value(state, self._sensor_handles[key]), 4
                )
            
            key = f"{zone}_occupancy"
            if key in self._sensor_handles:
                zone_data["occupancy"] = int(
                    self.api.exchange.get_variable_value(state, self._sensor_handles[key])
                )
            
            # Calculate a simplified PMV based on temperature deviation from 22°C
            temp = zone_data.get("temp_c", 22)
            zone_data["pmv"] = round((temp - 22.0) / 3.5, 2)  # Simplified PMV estimation
            
            # Track current setpoints
            with self._actuator_lock:
                zone_data["heating_sp"] = self._actuator_values.get(f"{zone}_heating_sp", 21.0)
                zone_data["cooling_sp"] = self._actuator_values.get(f"{zone}_cooling_sp", 24.0)
            
            data["zones"][zone] = zone_data
        
        # Outdoor data
        for sensor_key, data_key in [
            ("outdoor_temp", "temp_c"),
            ("outdoor_humidity", "humidity_pct"),
            ("outdoor_wind", "wind_speed_ms"),
            ("outdoor_solar", "solar_w_m2"),
        ]:
            if sensor_key in self._sensor_handles:
                data["outdoor"][data_key] = round(
                    self.api.exchange.get_variable_value(state, self._sensor_handles[sensor_key]), 2
                )
        
        # Energy data (variables return Watts directly, meter returns Joules)
        for sensor_key, data_key in [
            ("facility_energy", "total_w"),
            ("hvac_energy", "hvac_w"),
        ]:
            if sensor_key in self._sensor_handles:
                watts = self.api.exchange.get_variable_value(state, self._sensor_handles[sensor_key])
                data["energy"][data_key] = round(watts, 1)
                
        if "lighting_energy" in self._sensor_handles:
            timestep_seconds = 3600.0 / self.api.exchange.num_time_steps_in_hour(state)
            joules = self.api.exchange.get_meter_value(state, self._sensor_handles["lighting_energy"])
            watts = joules / timestep_seconds if timestep_seconds > 0 else 0
            data["energy"]["lighting_w"] = round(watts, 1)
        
        # Cumulative energy
        facility_w = data["energy"].get("total_w", 0)
        # Watts to kWh for this timestep (W * 15min / 60min / 1000)
        timestep_kwh = facility_w * 0.25 / 1000.0
        self._cumulative_energy_j += timestep_kwh * 3_600_000 # Keep variable name same but store J equiv for property
        
        data["energy"]["cumulative_kwh"] = round(self._cumulative_energy_j / 3_600_000, 2)
        data["energy"]["total_energy_kwh"] = round(timestep_kwh, 4)
        
        return data

    def _apply_actuator_values(self, state):
        """Apply pending actuator overrides to the simulation."""
        with self._actuator_lock:
            for key, value in self._actuator_values.items():
                if key in self._actuator_handles:
                    self.api.exchange.set_actuator_value(
                        state, self._actuator_handles[key], value
                    )

    def set_actuator(self, name: str, value: float):
        """Thread-safe method to set an actuator value for the next timestep."""
        with self._actuator_lock:
            self._actuator_values[name] = value

    def get_latest_sensor_data(self) -> Dict[str, Any]:
        """Get the most recent sensor data (thread-safe)."""
        with self._data_lock:
            return self._sensor_data.copy()

    def get_sensor_data_from_queue(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Get sensor data from the queue (blocks until available)."""
        try:
            return self._data_queue.get(timeout=timeout)
        except Empty:
            return None

    def run_simulation(self, idf_path: str, epw_path: str, 
                       output_dir: str = "output/sim_results",
                       enable_control: bool = False) -> bool:
        """
        Run an EnergyPlus simulation.
        
        Args:
            idf_path: Path to the IDF building model file
            epw_path: Path to the EPW weather file
            output_dir: Directory for simulation output
            enable_control: If True, register the control callback
            
        Returns:
            True if simulation completed successfully
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Create a new state for this simulation
        self.state = self.api.state_manager.new_state()
        self._handles_initialized = False
        self._timestep_count = 0
        self._cumulative_energy_j = 0.0
        self._sensor_data = {}
        self._sim_running = True
        
        if enable_control:
            # Register callback at end of system timestep (meters are updated)
            self.api.runtime.callback_end_system_timestep_after_hvac_reporting(
                self.state, self._timestep_callback
            )
        
        # Build command-line args for EnergyPlus
        args = [
            "-w", epw_path,
            "-d", output_dir,
            "-r",  # Read vars
            idf_path
        ]
        
        print(f"[EP] Starting simulation: {os.path.basename(idf_path)}")
        print(f"[EP] Weather: {os.path.basename(epw_path)}")
        print(f"[EP] Output: {output_dir}")
        print(f"[EP] Control enabled: {enable_control}")
        
        # Run the simulation (blocking)
        exit_code = self.api.runtime.run_energyplus(self.state, args)
        
        self._sim_running = False
        
        # Cleanup
        self.api.state_manager.delete_state(self.state)
        self.state = None
        
        success = (exit_code == 0)
        if success:
            print(f"[EP] Simulation completed successfully. "
                  f"{self._timestep_count} timesteps processed.")
        else:
            print(f"[EP] Simulation failed with exit code {exit_code}")
        
        return success

    @property
    def is_running(self) -> bool:
        return self._sim_running

    @property
    def timestep_count(self) -> int:
        return self._timestep_count

    @property
    def cumulative_energy_kwh(self) -> float:
        return round(self._cumulative_energy_j / 3_600_000, 2)
