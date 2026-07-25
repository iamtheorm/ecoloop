"""
create_model.py — Create the baseline building model from EnergyPlus example files.
Modifies the 5ZoneAirCooled example to serve as our baseline office building.
"""

import os
import sys
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_PATH = os.path.join(PROJECT_ROOT, "energyplus")
sys.path.insert(0, PROJECT_ROOT)

from eppy.modeleditor import IDF

IDD_FILE = os.path.join(EP_PATH, "Energy+.idd")
EXAMPLE_IDF = os.path.join(EP_PATH, "ExampleFiles", "5ZoneAirCooled.idf")
EPW_FILE = os.path.join(EP_PATH, "WeatherData",
                        "USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw")
OUTPUT_IDF = os.path.join(PROJECT_ROOT, "models", "baseline_office.idf")


def create_baseline_model():
    """Create the baseline building model from example."""
    IDF.setiddname(IDD_FILE)
    idf = IDF(EXAMPLE_IDF, EPW_FILE)
    
    print("[Model] Loaded 5ZoneAirCooled example")
    
    # === Modify Building Name ===
    building = idf.idfobjects["BUILDING"][0]
    building.Name = "EcoLoop_Office_Building"
    
    # === Modify Run Period to 1 week in summer ===
    # Remove existing run periods
    while idf.idfobjects["RUNPERIOD"]:
        idf.popidfobject("RUNPERIOD", 0)
    
    rp = idf.newidfobject("RUNPERIOD")
    rp.Name = "SummerWeek"
    rp.Begin_Month = 7
    rp.Begin_Day_of_Month = 15
    rp.End_Month = 7
    rp.End_Day_of_Month = 21
    rp.Day_of_Week_for_Start_Day = "Monday"
    rp.Use_Weather_File_Holidays_and_Special_Days = "No"
    rp.Use_Weather_File_Daylight_Saving_Period = "No"
    rp.Apply_Weekend_Holiday_Rule = "No"
    rp.Use_Weather_File_Rain_Indicators = "Yes"
    rp.Use_Weather_File_Snow_Indicators = "Yes"
    
    # === Add comprehensive output variables ===
    # Remove existing output variables (clean slate)
    while idf.idfobjects["OUTPUT:VARIABLE"]:
        idf.popidfobject("OUTPUT:VARIABLE", 0)
    
    output_vars = [
        ("Zone Mean Air Temperature", "*"),
        ("Zone Mean Air Humidity Ratio", "*"),
        ("Zone People Occupant Count", "*"),
        ("Site Outdoor Air Drybulb Temperature", "*"),
        ("Site Outdoor Air Relative Humidity", "*"),
        ("Site Wind Speed", "*"),
        ("Site Direct Solar Radiation Rate per Area", "*"),
        ("Zone Ideal Loads Supply Air Total Heating Energy", "*"),
        ("Zone Ideal Loads Supply Air Total Cooling Energy", "*"),
        ("Zone Air System Sensible Cooling Energy", "*"),
        ("Zone Air System Sensible Heating Energy", "*"),
        ("Facility Total Building Electricity Demand Rate", "*"),
        ("Facility Total HVAC Electricity Demand Rate", "*"),
    ]
    
    for var_name, key in output_vars:
        ov = idf.newidfobject("OUTPUT:VARIABLE")
        ov.Key_Value = key
        ov.Variable_Name = var_name
        ov.Reporting_Frequency = "Timestep"
    
    # === Add output meters ===
    while idf.idfobjects.get("OUTPUT:METER", []):
        idf.popidfobject("OUTPUT:METER", 0)
    
    meters = [
        "Electricity:Facility",
        "Electricity:HVAC",
        "InteriorLights:Electricity",
    ]
    for meter_name in meters:
        om = idf.newidfobject("OUTPUT:METER")
        om.Key_Name = meter_name
        om.Reporting_Frequency = "Timestep"
    
    # === Add EMS Output ===
    while idf.idfobjects.get("OUTPUT:ENERGYMANAGEMENTSYSTEM", []):
        idf.popidfobject("OUTPUT:ENERGYMANAGEMENTSYSTEM", 0)
    
    ems_out = idf.newidfobject("OUTPUT:ENERGYMANAGEMENTSYSTEM")
    ems_out.Actuator_Availability_Dictionary_Reporting = "Verbose"
    ems_out.Internal_Variable_Availability_Dictionary_Reporting = "Verbose"
    ems_out.EMS_Runtime_Language_Debug_Output_Level = "ErrorsOnly"

    # === Save ===
    os.makedirs(os.path.dirname(OUTPUT_IDF), exist_ok=True)
    idf.saveas(OUTPUT_IDF)
    
    # List zones for reference
    zones = [z.Name for z in idf.idfobjects["ZONE"]]
    print(f"[Model] Zones: {zones}")
    print(f"[Model] Saved baseline model to: {OUTPUT_IDF}")
    
    # Copy weather file to models directory
    weather_dest = os.path.join(PROJECT_ROOT, "models", "weather", "weather.epw")
    os.makedirs(os.path.dirname(weather_dest), exist_ok=True)
    shutil.copy(EPW_FILE, weather_dest)
    print(f"[Model] Copied weather file to: {weather_dest}")
    
    return zones


if __name__ == "__main__":
    zones = create_baseline_model()
    print(f"\nDone! Zones available for control: {zones}")
