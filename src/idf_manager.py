"""
idf_manager.py — Parse and modify EnergyPlus IDF files using eppy.
Handles building model configuration, output variable setup, and setpoint management.
"""

import os
import sys
from typing import List, Dict, Any, Optional

# Add energyplus to path for IDD
EP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "energyplus")
IDD_FILE = os.path.join(EP_PATH, "Energy+.idd")


class IDFManager:
    """Manages EnergyPlus IDF files using eppy for parsing and modification."""

    def __init__(self, idd_path: str = None):
        """
        Initialize the IDF Manager.
        
        Args:
            idd_path: Path to Energy+.idd file. Auto-detects if None.
        """
        from eppy.modeleditor import IDF
        self.IDF = IDF
        
        idd = idd_path or IDD_FILE
        if not os.path.exists(idd):
            raise FileNotFoundError(f"Energy+.idd not found at {idd}")
        
        try:
            IDF.setiddname(idd)
        except Exception:
            pass  # IDD already set
        
        self.idf = None
        self.filepath = None

    def load_idf(self, filepath: str, epw_path: str = None):
        """Load an IDF file."""
        self.filepath = filepath
        self.idf = self.IDF(filepath, epw_path)
        print(f"[IDF] Loaded: {os.path.basename(filepath)}")

    def get_zones(self) -> List[str]:
        """Get all thermal zone names."""
        zones = self.idf.idfobjects["ZONE"]
        return [z.Name for z in zones]

    def get_building_info(self) -> Dict[str, Any]:
        """Get basic building information."""
        building = self.idf.idfobjects["BUILDING"]
        info = {"name": "Unknown", "zones": self.get_zones()}
        if building:
            info["name"] = building[0].Name
        return info

    def add_output_variables(self, zone_names: List[str]):
        """Add required output variables for monitoring."""
        # List of output variables we need
        variables = [
            ("Zone Mean Air Temperature", "*"),
            ("Zone Mean Air Humidity Ratio", "*"),
            ("Zone People Occupant Count", "*"),
            ("Site Outdoor Air Drybulb Temperature", "*"),
            ("Site Outdoor Air Relative Humidity", "*"),
            ("Site Wind Speed", "*"),
            ("Site Direct Solar Radiation Rate per Area", "*"),
            ("Zone Ideal Loads Supply Air Total Heating Energy", "*"),
            ("Zone Ideal Loads Supply Air Total Cooling Energy", "*"),
        ]
        
        # Add output variables
        for var_name, key in variables:
            obj = self.idf.newidfobject("OUTPUT:VARIABLE")
            obj.Key_Value = key
            obj.Variable_Name = var_name
            obj.Reporting_Frequency = "Timestep"
        
        # Add output meters
        meters = [
            "Electricity:Facility",
            "Electricity:HVAC",
            "InteriorLights:Electricity",
            "Heating:Electricity",
            "Cooling:Electricity",
        ]
        for meter_name in meters:
            obj = self.idf.newidfobject("OUTPUT:METER")
            obj.Key_Name = meter_name
            obj.Reporting_Frequency = "Timestep"
        
        print(f"[IDF] Added {len(variables)} output variables, {len(meters)} meters")

    def save(self, filepath: str = None):
        """Save the IDF file."""
        path = filepath or self.filepath
        self.idf.saveas(path)
        print(f"[IDF] Saved: {os.path.basename(path)}")


def create_baseline_office_idf(output_path: str, epw_path: str = None) -> str:
    """
    Create a baseline 3-zone office building IDF file.
    Uses EnergyPlus IdealLoads for HVAC to keep the model simple but functional.
    
    Returns:
        Path to the created IDF file
    """
    from eppy.modeleditor import IDF
    
    idd = IDD_FILE
    try:
        IDF.setiddname(idd)
    except:
        pass
    
    idf = IDF()
    
    # ===== VERSION =====
    ver = idf.newidfobject("VERSION")
    ver.Version_Identifier = "24.1"
    
    # ===== SIMULATION PARAMETERS =====
    sim = idf.newidfobject("SIMULATIONCONTROL")
    sim.Do_Zone_Sizing_Calculation = "Yes"
    sim.Do_System_Sizing_Calculation = "No"
    sim.Do_Plant_Sizing_Calculation = "No"
    sim.Run_Simulation_for_Sizing_Periods = "No"
    sim.Run_Simulation_for_Weather_File_Run_Periods = "Yes"
    
    # Building
    bldg = idf.newidfobject("BUILDING")
    bldg.Name = "EcoLoop_Office"
    bldg.North_Axis = 0
    bldg.Terrain = "City"
    bldg.Loads_Convergence_Tolerance_Value = 0.04
    bldg.Temperature_Convergence_Tolerance_Value = 0.4
    bldg.Solar_Distribution = "FullExterior"
    bldg.Maximum_Number_of_Warmup_Days = 25
    
    # Timestep (4 per hour = 15 min intervals)
    ts = idf.newidfobject("TIMESTEP")
    ts.Number_of_Timesteps_per_Hour = 4
    
    # Run period — 1 week in summer (Jul 15-21) for quick simulation
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
    
    # ===== SCHEDULES =====
    # Schedule types
    st_frac = idf.newidfobject("SCHEDULETYPELIMITS")
    st_frac.Name = "Fraction"
    st_frac.Lower_Limit_Value = 0
    st_frac.Upper_Limit_Value = 1
    st_frac.Numeric_Type = "Continuous"
    
    st_temp = idf.newidfobject("SCHEDULETYPELIMITS")
    st_temp.Name = "Temperature"
    st_temp.Lower_Limit_Value = -100
    st_temp.Upper_Limit_Value = 200
    st_temp.Numeric_Type = "Continuous"
    
    st_any = idf.newidfobject("SCHEDULETYPELIMITS")
    st_any.Name = "Any Number"
    st_any.Numeric_Type = "Continuous"
    
    st_onoff = idf.newidfobject("SCHEDULETYPELIMITS")
    st_onoff.Name = "On/Off"
    st_onoff.Lower_Limit_Value = 0
    st_onoff.Upper_Limit_Value = 1
    st_onoff.Numeric_Type = "Discrete"
    
    # Occupancy schedule (weekday 8-18, weekend off)
    occ = idf.newidfobject("SCHEDULE:COMPACT")
    occ.Name = "Office_Occupancy"
    occ.Schedule_Type_Limits_Name = "Fraction"
    occ.Field_1 = "Through: 12/31"
    occ.Field_2 = "For: Weekdays"
    occ.Field_3 = "Until: 07:00, 0.0"
    occ.Field_4 = "Until: 08:00, 0.5"
    occ.Field_5 = "Until: 12:00, 1.0"
    occ.Field_6 = "Until: 13:00, 0.8"
    occ.Field_7 = "Until: 17:00, 1.0"
    occ.Field_8 = "Until: 18:00, 0.5"
    occ.Field_9 = "Until: 24:00, 0.0"
    occ.Field_10 = "For: AllOtherDays"
    occ.Field_11 = "Until: 24:00, 0.0"
    
    # Lighting schedule
    light = idf.newidfobject("SCHEDULE:COMPACT")
    light.Name = "Office_Lighting"
    light.Schedule_Type_Limits_Name = "Fraction"
    light.Field_1 = "Through: 12/31"
    light.Field_2 = "For: Weekdays"
    light.Field_3 = "Until: 07:00, 0.1"
    light.Field_4 = "Until: 08:00, 0.5"
    light.Field_5 = "Until: 18:00, 1.0"
    light.Field_6 = "Until: 19:00, 0.5"
    light.Field_7 = "Until: 24:00, 0.1"
    light.Field_8 = "For: AllOtherDays"
    light.Field_9 = "Until: 24:00, 0.1"
    
    # Equipment schedule
    equip = idf.newidfobject("SCHEDULE:COMPACT")
    equip.Name = "Office_Equipment"
    equip.Schedule_Type_Limits_Name = "Fraction"
    equip.Field_1 = "Through: 12/31"
    equip.Field_2 = "For: Weekdays"
    equip.Field_3 = "Until: 07:00, 0.2"
    equip.Field_4 = "Until: 08:00, 0.5"
    equip.Field_5 = "Until: 18:00, 1.0"
    equip.Field_6 = "Until: 19:00, 0.5"
    equip.Field_7 = "Until: 24:00, 0.2"
    equip.Field_8 = "For: AllOtherDays"
    equip.Field_9 = "Until: 24:00, 0.2"
    
    # Activity schedule (120 W/person metabolic rate)
    activity = idf.newidfobject("SCHEDULE:COMPACT")
    activity.Name = "Activity_Schedule"
    activity.Schedule_Type_Limits_Name = "Any Number"
    activity.Field_1 = "Through: 12/31"
    activity.Field_2 = "For: AllDays"
    activity.Field_3 = "Until: 24:00, 120"
    
    # Work efficiency schedule
    work_eff = idf.newidfobject("SCHEDULE:COMPACT")
    work_eff.Name = "Work_Efficiency"
    work_eff.Schedule_Type_Limits_Name = "Fraction"
    work_eff.Field_1 = "Through: 12/31"
    work_eff.Field_2 = "For: AllDays"
    work_eff.Field_3 = "Until: 24:00, 0.0"
    
    # Clothing schedule (0.5 clo summer)
    clothing = idf.newidfobject("SCHEDULE:COMPACT")
    clothing.Name = "Clothing_Schedule"
    clothing.Schedule_Type_Limits_Name = "Any Number"
    clothing.Field_1 = "Through: 12/31"
    clothing.Field_2 = "For: AllDays"
    clothing.Field_3 = "Until: 24:00, 0.5"
    
    # Air velocity schedule
    air_vel = idf.newidfobject("SCHEDULE:COMPACT")
    air_vel.Name = "Air_Velocity"
    air_vel.Schedule_Type_Limits_Name = "Any Number"
    air_vel.Field_1 = "Through: 12/31"
    air_vel.Field_2 = "For: AllDays"
    air_vel.Field_3 = "Until: 24:00, 0.1"
    
    # HVAC availability (always on)
    avail = idf.newidfobject("SCHEDULE:COMPACT")
    avail.Name = "HVAC_Always_On"
    avail.Schedule_Type_Limits_Name = "On/Off"
    avail.Field_1 = "Through: 12/31"
    avail.Field_2 = "For: AllDays"
    avail.Field_3 = "Until: 24:00, 1"
    
    # Baseline Heating setpoint schedule (fixed 21°C)
    heat_sp = idf.newidfobject("SCHEDULE:COMPACT")
    heat_sp.Name = "Heating_Setpoint_Schedule"
    heat_sp.Schedule_Type_Limits_Name = "Temperature"
    heat_sp.Field_1 = "Through: 12/31"
    heat_sp.Field_2 = "For: Weekdays"
    heat_sp.Field_3 = "Until: 07:00, 16.0"
    heat_sp.Field_4 = "Until: 18:00, 21.0"
    heat_sp.Field_5 = "Until: 24:00, 16.0"
    heat_sp.Field_6 = "For: AllOtherDays"
    heat_sp.Field_7 = "Until: 24:00, 16.0"
    
    # Baseline Cooling setpoint schedule (fixed 24°C)
    cool_sp = idf.newidfobject("SCHEDULE:COMPACT")
    cool_sp.Name = "Cooling_Setpoint_Schedule"
    cool_sp.Schedule_Type_Limits_Name = "Temperature"
    cool_sp.Field_1 = "Through: 12/31"
    cool_sp.Field_2 = "For: Weekdays"
    cool_sp.Field_3 = "Until: 07:00, 28.0"
    cool_sp.Field_4 = "Until: 18:00, 24.0"
    cool_sp.Field_5 = "Until: 24:00, 28.0"
    cool_sp.Field_6 = "For: AllOtherDays"
    cool_sp.Field_7 = "Until: 24:00, 28.0"
    
    # Per-zone light schedules (for actuator control)
    zone_configs = [
        ("OpenOffice", 200, 3.0, 20, 10, 10.8),
        ("ConferenceRoom", 50, 3.0, 10, 13, 5.0),
        ("ServerRoom", 30, 3.0, 2, 15, 8.0),
    ]
    
    for zone_name, area, height, people, equip_wperm2, light_wperm2 in zone_configs:
        sched = idf.newidfobject("SCHEDULE:COMPACT")
        sched.Name = f"{zone_name}_Lights_Schedule"
        sched.Schedule_Type_Limits_Name = "Fraction"
        sched.Field_1 = "Through: 12/31"
        sched.Field_2 = "For: Weekdays"
        sched.Field_3 = "Until: 07:00, 0.1"
        sched.Field_4 = "Until: 08:00, 0.5"
        sched.Field_5 = "Until: 18:00, 1.0"
        sched.Field_6 = "Until: 19:00, 0.5"
        sched.Field_7 = "Until: 24:00, 0.1"
        sched.Field_8 = "For: AllOtherDays"
        sched.Field_9 = "Until: 24:00, 0.1"
    
    # ===== GLOBAL GEOMETRY RULES =====
    geo = idf.newidfobject("GLOBALGEOMETRYRULES")
    geo.Starting_Vertex_Position = "UpperLeftCorner"
    geo.Vertex_Entry_Direction = "Counterclockwise"
    geo.Coordinate_System = "Relative"
    
    # ===== ZONES AND SURFACES =====
    # Zone 1: OpenOffice (10m x 20m x 3m = 200 m²)
    z1 = idf.newidfobject("ZONE")
    z1.Name = "OpenOffice"
    z1.Direction_of_Relative_North = 0
    z1.X_Origin = 0
    z1.Y_Origin = 0
    z1.Z_Origin = 0
    
    # Zone 2: ConferenceRoom (10m x 5m x 3m = 50 m²)
    z2 = idf.newidfobject("ZONE")
    z2.Name = "ConferenceRoom"
    z2.Direction_of_Relative_North = 0
    z2.X_Origin = 20
    z2.Y_Origin = 0
    z2.Z_Origin = 0
    
    # Zone 3: ServerRoom (6m x 5m x 3m = 30 m²)
    z3 = idf.newidfobject("ZONE")
    z3.Name = "ServerRoom"
    z3.Direction_of_Relative_North = 0
    z3.X_Origin = 20
    z3.Y_Origin = 5
    z3.Z_Origin = 0
    
    # ===== SURFACES =====
    # Create simple box surfaces for each zone
    _create_zone_surfaces(idf, "OpenOffice", 0, 0, 0, 20, 10, 3)
    _create_zone_surfaces(idf, "ConferenceRoom", 20, 0, 0, 10, 5, 3)
    _create_zone_surfaces(idf, "ServerRoom", 20, 5, 0, 6, 5, 3)
    
    # ===== CONSTRUCTION & MATERIALS =====
    # Simple material
    mat_wall = idf.newidfobject("MATERIAL")
    mat_wall.Name = "WallMaterial"
    mat_wall.Roughness = "MediumRough"
    mat_wall.Thickness = 0.2
    mat_wall.Conductivity = 0.9
    mat_wall.Density = 1800
    mat_wall.Specific_Heat = 1000
    
    mat_roof = idf.newidfobject("MATERIAL")
    mat_roof.Name = "RoofMaterial"
    mat_roof.Roughness = "MediumRough"
    mat_roof.Thickness = 0.15
    mat_roof.Conductivity = 0.7
    mat_roof.Density = 1400
    mat_roof.Specific_Heat = 900
    
    mat_floor = idf.newidfobject("MATERIAL")
    mat_floor.Name = "FloorMaterial"
    mat_floor.Roughness = "MediumRough"
    mat_floor.Thickness = 0.2
    mat_floor.Conductivity = 1.4
    mat_floor.Density = 2400
    mat_floor.Specific_Heat = 880
    
    # Constructions
    con_wall = idf.newidfobject("CONSTRUCTION")
    con_wall.Name = "WallConstruction"
    con_wall.Outside_Layer = "WallMaterial"
    
    con_roof = idf.newidfobject("CONSTRUCTION")
    con_roof.Name = "RoofConstruction"
    con_roof.Outside_Layer = "RoofMaterial"
    
    con_floor = idf.newidfobject("CONSTRUCTION")
    con_floor.Name = "FloorConstruction"
    con_floor.Outside_Layer = "FloorMaterial"
    
    # Window material (simple glazing)
    win_mat = idf.newidfobject("WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM")
    win_mat.Name = "SimpleWindow"
    win_mat.UFactor = 2.0
    win_mat.Solar_Heat_Gain_Coefficient = 0.4
    
    con_win = idf.newidfobject("CONSTRUCTION")
    con_win.Name = "WindowConstruction"
    con_win.Outside_Layer = "SimpleWindow"
    
    # ===== INTERNAL LOADS =====
    for zone_name, area, height, people_count, equip_wperm2, light_wperm2 in zone_configs:
        # People
        ppl = idf.newidfobject("PEOPLE")
        ppl.Name = f"{zone_name}_People"
        ppl.Zone_or_ZoneList_or_Space_or_SpaceList_Name = zone_name
        ppl.Number_of_People_Schedule_Name = "Office_Occupancy"
        ppl.Number_of_People_Calculation_Method = "People"
        ppl.Number_of_People = people_count
        ppl.Fraction_Radiant = 0.3
        ppl.Activity_Level_Schedule_Name = "Activity_Schedule"
        ppl.Work_Efficiency_Schedule_Name = "Work_Efficiency"
        ppl.Clothing_Insulation_Schedule_Name = "Clothing_Schedule"
        ppl.Air_Velocity_Schedule_Name = "Air_Velocity"
        
        # Lights
        lgt = idf.newidfobject("LIGHTS")
        lgt.Name = f"{zone_name}_Lights"
        lgt.Zone_or_ZoneList_or_Space_or_SpaceList_Name = zone_name
        lgt.Schedule_Name = f"{zone_name}_Lights_Schedule"
        lgt.Design_Level_Calculation_Method = "Watts/Area"
        lgt.Watts_per_Zone_Floor_Area = light_wperm2
        lgt.Fraction_Radiant = 0.42
        lgt.Fraction_Visible = 0.18
        lgt.Return_Air_Fraction = 0.0
        
        # Equipment
        eqp = idf.newidfobject("ELECTRICEQUIPMENT")
        eqp.Name = f"{zone_name}_Equipment"
        eqp.Zone_or_ZoneList_or_Space_or_SpaceList_Name = zone_name
        eqp.Schedule_Name = "Office_Equipment"
        eqp.Design_Level_Calculation_Method = "Watts/Area"
        eqp.Watts_per_Zone_Floor_Area = equip_wperm2
        eqp.Fraction_Radiant = 0.3
        eqp.Fraction_Latent = 0.0
        eqp.Fraction_Lost = 0.0
    
    # ===== HVAC: Ideal Loads Air System =====
    for zone_name, _, _, _, _, _ in zone_configs:
        # Thermostat
        tstat = idf.newidfobject("ZONECONTROL:THERMOSTAT")
        tstat.Name = f"{zone_name}_Thermostat"
        tstat.Zone_or_ZoneList_Name = zone_name
        tstat.Control_Type_Schedule_Name = "HVAC_Always_On"
        tstat.Control_1_Object_Type = "ThermostatSetpoint:DualSetpoint"
        tstat.Control_1_Name = f"{zone_name}_DualSetpoint"
        
        # Dual setpoint
        dsp = idf.newidfobject("THERMOSTATSETPOINT:DUALSETPOINT")
        dsp.Name = f"{zone_name}_DualSetpoint"
        dsp.Heating_Setpoint_Temperature_Schedule_Name = "Heating_Setpoint_Schedule"
        dsp.Cooling_Setpoint_Temperature_Schedule_Name = "Cooling_Setpoint_Schedule"
        
        # Ideal Loads (simplified HVAC)
        ideal = idf.newidfobject("ZONEHVAC:IDEALLOADSAIRSYSTEM")
        ideal.Name = f"{zone_name}_IdealLoads"
        ideal.Availability_Schedule_Name = "HVAC_Always_On"
        ideal.Zone_Supply_Air_Node_Name = f"{zone_name}_SupplyNode"
        ideal.Maximum_Heating_Supply_Air_Temperature = 50
        ideal.Minimum_Cooling_Supply_Air_Temperature = 13
        ideal.Maximum_Heating_Supply_Air_Humidity_Ratio = 0.0156
        ideal.Minimum_Cooling_Supply_Air_Humidity_Ratio = 0.0077
        ideal.Heating_Limit = "NoLimit"
        ideal.Cooling_Limit = "NoLimit"
        ideal.Dehumidification_Control_Type = "None"
        ideal.Humidification_Control_Type = "None"
        
        # Equipment list
        eq_list = idf.newidfobject("ZONEHVAC:EQUIPMENTLIST")
        eq_list.Name = f"{zone_name}_EquipList"
        eq_list.Zone_Equipment_1_Object_Type = "ZoneHVAC:IdealLoadsAirSystem"
        eq_list.Zone_Equipment_1_Name = f"{zone_name}_IdealLoads"
        eq_list.Zone_Equipment_1_Cooling_Sequence = 1
        eq_list.Zone_Equipment_1_Heating_or_NoLoad_Sequence = 1
        
        # Equipment connections
        eq_conn = idf.newidfobject("ZONEHVAC:EQUIPMENTCONNECTIONS")
        eq_conn.Zone_Name = zone_name
        eq_conn.Zone_Conditioning_Equipment_List_Name = f"{zone_name}_EquipList"
        eq_conn.Zone_Air_Inlet_Node_or_NodeList_Name = f"{zone_name}_SupplyNode"
        eq_conn.Zone_Air_Node_Name = f"{zone_name}_ZoneAirNode"
        eq_conn.Zone_Return_Air_Node_or_NodeList_Name = f"{zone_name}_ReturnNode"
    
    # Thermostat control type schedule (4 = dual setpoint)
    ctrl_sched = idf.newidfobject("SCHEDULE:COMPACT")
    ctrl_sched.Name = "HVAC_Always_On"
    # Already exists above, but we need the control type value 4
    # Let's use a separate schedule for control type
    ctrl_type = idf.newidfobject("SCHEDULE:COMPACT")
    ctrl_type.Name = "Control_Type_Schedule"
    ctrl_type.Schedule_Type_Limits_Name = "Any Number"
    ctrl_type.Field_1 = "Through: 12/31"
    ctrl_type.Field_2 = "For: AllDays"
    ctrl_type.Field_3 = "Until: 24:00, 4"
    
    # Fix thermostat references to use control type schedule
    for tstat in idf.idfobjects["ZONECONTROL:THERMOSTAT"]:
        tstat.Control_Type_Schedule_Name = "Control_Type_Schedule"
    
    # ===== OUTPUT VARIABLES =====
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
    ]
    
    for var_name, key in output_vars:
        ov = idf.newidfobject("OUTPUT:VARIABLE")
        ov.Key_Value = key
        ov.Variable_Name = var_name
        ov.Reporting_Frequency = "Timestep"
    
    # Output meters
    for meter in ["Electricity:Facility", "Electricity:HVAC",
                   "InteriorLights:Electricity"]:
        om = idf.newidfobject("OUTPUT:METER")
        om.Key_Name = meter
        om.Reporting_Frequency = "Timestep"
    
    # Output control
    oc = idf.newidfobject("OUTPUTCONTROL:TABLE:STYLE")
    oc.Column_Separator = "HTML"
    
    ot = idf.newidfobject("OUTPUT:TABLE:SUMMARYREPORTS")
    ot.Report_1 = "AllSummary"
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    idf.saveas(output_path)
    print(f"[IDF] Created baseline building: {output_path}")
    return output_path


def _create_zone_surfaces(idf, zone_name: str, 
                           x0: float, y0: float, z0: float,
                           width: float, depth: float, height: float):
    """Create box surfaces for a zone (floor, ceiling, 4 walls with a south window)."""
    
    x1, y1 = x0 + width, y0 + depth
    z1 = z0 + height
    
    # Floor
    floor = idf.newidfobject("BUILDINGSURFACE:DETAILED")
    floor.Name = f"{zone_name}_Floor"
    floor.Surface_Type = "Floor"
    floor.Construction_Name = "FloorConstruction"
    floor.Zone_Name = zone_name
    floor.Outside_Boundary_Condition = "Ground"
    floor.Sun_Exposure = "NoSun"
    floor.Wind_Exposure = "NoWind"
    floor.Number_of_Vertices = 4
    floor.Vertex_1_Xcoordinate = x0
    floor.Vertex_1_Ycoordinate = y1
    floor.Vertex_1_Zcoordinate = z0
    floor.Vertex_2_Xcoordinate = x0
    floor.Vertex_2_Ycoordinate = y0
    floor.Vertex_2_Zcoordinate = z0
    floor.Vertex_3_Xcoordinate = x1
    floor.Vertex_3_Ycoordinate = y0
    floor.Vertex_3_Zcoordinate = z0
    floor.Vertex_4_Xcoordinate = x1
    floor.Vertex_4_Ycoordinate = y1
    floor.Vertex_4_Zcoordinate = z0
    
    # Ceiling/Roof
    roof = idf.newidfobject("BUILDINGSURFACE:DETAILED")
    roof.Name = f"{zone_name}_Roof"
    roof.Surface_Type = "Roof"
    roof.Construction_Name = "RoofConstruction"
    roof.Zone_Name = zone_name
    roof.Outside_Boundary_Condition = "Outdoors"
    roof.Sun_Exposure = "SunExposed"
    roof.Wind_Exposure = "WindExposed"
    roof.Number_of_Vertices = 4
    roof.Vertex_1_Xcoordinate = x0
    roof.Vertex_1_Ycoordinate = y0
    roof.Vertex_1_Zcoordinate = z1
    roof.Vertex_2_Xcoordinate = x0
    roof.Vertex_2_Ycoordinate = y1
    roof.Vertex_2_Zcoordinate = z1
    roof.Vertex_3_Xcoordinate = x1
    roof.Vertex_3_Ycoordinate = y1
    roof.Vertex_3_Zcoordinate = z1
    roof.Vertex_4_Xcoordinate = x1
    roof.Vertex_4_Ycoordinate = y0
    roof.Vertex_4_Zcoordinate = z1
    
    # South wall (with window)
    south = idf.newidfobject("BUILDINGSURFACE:DETAILED")
    south.Name = f"{zone_name}_SouthWall"
    south.Surface_Type = "Wall"
    south.Construction_Name = "WallConstruction"
    south.Zone_Name = zone_name
    south.Outside_Boundary_Condition = "Outdoors"
    south.Sun_Exposure = "SunExposed"
    south.Wind_Exposure = "WindExposed"
    south.Number_of_Vertices = 4
    south.Vertex_1_Xcoordinate = x0
    south.Vertex_1_Ycoordinate = y0
    south.Vertex_1_Zcoordinate = z1
    south.Vertex_2_Xcoordinate = x0
    south.Vertex_2_Ycoordinate = y0
    south.Vertex_2_Zcoordinate = z0
    south.Vertex_3_Xcoordinate = x1
    south.Vertex_3_Ycoordinate = y0
    south.Vertex_3_Zcoordinate = z0
    south.Vertex_4_Xcoordinate = x1
    south.Vertex_4_Ycoordinate = y0
    south.Vertex_4_Zcoordinate = z1
    
    # Window on south wall
    win_x0 = x0 + width * 0.1
    win_x1 = x0 + width * 0.9
    win_z0 = z0 + 0.8
    win_z1 = z0 + height - 0.3
    
    win = idf.newidfobject("FENESTRATIONSURFACE:DETAILED")
    win.Name = f"{zone_name}_Window"
    win.Surface_Type = "Window"
    win.Construction_Name = "WindowConstruction"
    win.Building_Surface_Name = f"{zone_name}_SouthWall"
    win.Number_of_Vertices = 4
    win.Vertex_1_Xcoordinate = win_x0
    win.Vertex_1_Ycoordinate = y0
    win.Vertex_1_Zcoordinate = win_z1
    win.Vertex_2_Xcoordinate = win_x0
    win.Vertex_2_Ycoordinate = y0
    win.Vertex_2_Zcoordinate = win_z0
    win.Vertex_3_Xcoordinate = win_x1
    win.Vertex_3_Ycoordinate = y0
    win.Vertex_3_Zcoordinate = win_z0
    win.Vertex_4_Xcoordinate = win_x1
    win.Vertex_4_Ycoordinate = y0
    win.Vertex_4_Zcoordinate = win_z1
    
    # North wall
    north = idf.newidfobject("BUILDINGSURFACE:DETAILED")
    north.Name = f"{zone_name}_NorthWall"
    north.Surface_Type = "Wall"
    north.Construction_Name = "WallConstruction"
    north.Zone_Name = zone_name
    north.Outside_Boundary_Condition = "Outdoors"
    north.Sun_Exposure = "SunExposed"
    north.Wind_Exposure = "WindExposed"
    north.Number_of_Vertices = 4
    north.Vertex_1_Xcoordinate = x1
    north.Vertex_1_Ycoordinate = y1
    north.Vertex_1_Zcoordinate = z1
    north.Vertex_2_Xcoordinate = x1
    north.Vertex_2_Ycoordinate = y1
    north.Vertex_2_Zcoordinate = z0
    north.Vertex_3_Xcoordinate = x0
    north.Vertex_3_Ycoordinate = y1
    north.Vertex_3_Zcoordinate = z0
    north.Vertex_4_Xcoordinate = x0
    north.Vertex_4_Ycoordinate = y1
    north.Vertex_4_Zcoordinate = z1
    
    # East wall
    east = idf.newidfobject("BUILDINGSURFACE:DETAILED")
    east.Name = f"{zone_name}_EastWall"
    east.Surface_Type = "Wall"
    east.Construction_Name = "WallConstruction"
    east.Zone_Name = zone_name
    east.Outside_Boundary_Condition = "Outdoors"
    east.Sun_Exposure = "SunExposed"
    east.Wind_Exposure = "WindExposed"
    east.Number_of_Vertices = 4
    east.Vertex_1_Xcoordinate = x1
    east.Vertex_1_Ycoordinate = y0
    east.Vertex_1_Zcoordinate = z1
    east.Vertex_2_Xcoordinate = x1
    east.Vertex_2_Ycoordinate = y0
    east.Vertex_2_Zcoordinate = z0
    east.Vertex_3_Xcoordinate = x1
    east.Vertex_3_Ycoordinate = y1
    east.Vertex_3_Zcoordinate = z0
    east.Vertex_4_Xcoordinate = x1
    east.Vertex_4_Ycoordinate = y1
    east.Vertex_4_Zcoordinate = z1
    
    # West wall
    west = idf.newidfobject("BUILDINGSURFACE:DETAILED")
    west.Name = f"{zone_name}_WestWall"
    west.Surface_Type = "Wall"
    west.Construction_Name = "WallConstruction"
    west.Zone_Name = zone_name
    west.Outside_Boundary_Condition = "Outdoors"
    west.Sun_Exposure = "SunExposed"
    west.Wind_Exposure = "WindExposed"
    west.Number_of_Vertices = 4
    west.Vertex_1_Xcoordinate = x0
    west.Vertex_1_Ycoordinate = y1
    west.Vertex_1_Zcoordinate = z1
    west.Vertex_2_Xcoordinate = x0
    west.Vertex_2_Ycoordinate = y1
    west.Vertex_2_Zcoordinate = z0
    west.Vertex_3_Xcoordinate = x0
    west.Vertex_3_Ycoordinate = y0
    west.Vertex_3_Zcoordinate = z0
    west.Vertex_4_Xcoordinate = x0
    west.Vertex_4_Ycoordinate = y0
    west.Vertex_4_Zcoordinate = z1


if __name__ == "__main__":
    # Create the baseline building
    epw = os.path.join(EP_PATH, "WeatherData", 
                       "USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw")
    create_baseline_office_idf("models/baseline_office.idf", epw)
    print("Done!")
