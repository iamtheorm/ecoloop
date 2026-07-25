import sys
sys.path.insert(0, "/Users/orm/ecoloop/energyplus")
from pyenergyplus.api import EnergyPlusAPI

api = EnergyPlusAPI()
state = api.state_manager.new_state()
api.exchange.request_variable(state, "Zone Mean Air Temperature", "SPACE1-1")

def callback_end_zone_timestep(state):
    if not api.exchange.api_data_fully_ready(state):
        return
    
    # Just print the actuators and meters ONCE and then abort
    if not hasattr(callback_end_zone_timestep, 'done'):
        callback_end_zone_timestep.done = True
        
        print("\n--- AVAILABLE METERS ---")
        meters = api.exchange.get_meter_names(state)
        print(meters)
        
        print("\n--- AVAILABLE ACTUATORS ---")
        actuators = api.exchange.get_actuator_names(state)
        print(actuators)
        
        sys.exit(0)

api.runtime.callback_end_zone_timestep_after_zone_reporting(state, callback_end_zone_timestep)

args = [
    "-w", "/Users/orm/ecoloop/energyplus/WeatherData/USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw",
    "-d", "/Users/orm/ecoloop/output/debug_api",
    "/Users/orm/ecoloop/models/baseline_office.idf"
]

api.runtime.run_energyplus(state, args)
