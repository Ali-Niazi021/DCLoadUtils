#!/usr/bin/env python3
"""
DL3021 Battery Mode Discovery Script

This script will test various SCPI commands to find the proper way to:
1. Set battery test mode
2. Configure battery test parameters
3. Set up proper current and voltage limits for battery testing

Based on common RIGOL DL3000 series commands from manuals.
"""

import pyvisa
import time

def discover_battery_mode():
    """Discover battery mode commands and settings"""
    
    visa_address = "USB0::0x1AB1::0x0E11::DL3A231800370::INSTR"
    
    try:
        print("DL3021 Battery Mode Discovery")
        print("=" * 40)
        
        # Connect to device
        rm = pyvisa.ResourceManager()
        instrument = rm.open_resource(visa_address)
        instrument.timeout = 5000
        
        print("Connected to device")
        print(f"Device: {instrument.query('*IDN?').strip()}")
        print()
        
        # Test application mode commands
        print("Testing Application Mode Commands:")
        print("-" * 35)
        
        app_mode_commands = [
            ("FUNC?", "Query current function"),
            ("FUNC:MODE?", "Query function mode"),
            ("APPL?", "Query application"),
            ("MODE?", "Query mode"),
            ("SYST:MODE?", "Query system mode"),
            ("FUNC CC", "Set Constant Current mode"),
            ("FUNC BATT", "Set Battery mode"),
            ("FUNC:BATT", "Set Battery function"),
            ("MODE BATT", "Set Battery mode"),
            ("APPL BATT", "Apply Battery mode"),
            ("APPL:BATT", "Apply Battery application"),
        ]
        
        for cmd, desc in app_mode_commands:
            test_command(instrument, cmd, desc)
        
        print("\nTesting Battery-Specific Commands:")
        print("-" * 38)
        
        battery_commands = [
            ("BATT?", "Query battery settings"),
            ("BATT:MODE?", "Query battery mode"),
            ("BATT:TYPE?", "Query battery type"),
            ("BATT:CAP?", "Query battery capacity"),
            ("BATT:VOLT?", "Query battery voltage settings"),
            ("BATT:CURR?", "Query battery current settings"),
            ("BATT:TIME?", "Query battery time settings"),
            ("BATT:TEMP?", "Query battery temperature"),
            ("BATT:TEST?", "Query battery test status"),
            ("BATT:STAT?", "Query battery status"),
            ("BATT:RES?", "Query battery resistance"),
        ]
        
        for cmd, desc in battery_commands:
            test_command(instrument, cmd, desc)
            
        print("\nTesting Current/Voltage Range Commands:")
        print("-" * 40)
        
        range_commands = [
            ("CURR:RANG?", "Query current range"),
            ("CURR:RANG LOW", "Set low current range"),
            ("CURR:RANG HIGH", "Set high current range"),
            ("VOLT:RANG?", "Query voltage range"),
            ("CURR:LEV?", "Query current level"),
            ("VOLT:LEV?", "Query voltage level"),
            ("POW:LEV?", "Query power level"),
        ]
        
        for cmd, desc in range_commands:
            test_command(instrument, cmd, desc)
            
        print("\nTesting List/Sequence Commands:")
        print("-" * 33)
        
        list_commands = [
            ("LIST?", "Query list settings"),
            ("LIST:MODE?", "Query list mode"),
            ("LIST:COUN?", "Query list count"),
            ("LIST:STEP?", "Query list step"),
            ("TRIG?", "Query trigger settings"),
            ("TRIG:SOUR?", "Query trigger source"),
        ]
        
        for cmd, desc in list_commands:
            test_command(instrument, cmd, desc)
            
        print("\nTesting Protection/Limit Commands:")
        print("-" * 36)
        
        protection_commands = [
            ("VOLT:PROT?", "Query voltage protection"),
            ("VOLT:PROT:STAT?", "Query voltage protection status"),
            ("CURR:PROT?", "Query current protection"),
            ("POW:PROT?", "Query power protection"),
            ("TEMP:PROT?", "Query temperature protection"),
            ("TIME:PROT?", "Query time protection"),
            ("RES:PROT?", "Query resistance protection"),
            ("VOLT:LIM?", "Query voltage limit"),
            ("CURR:LIM?", "Query current limit"),
        ]
        
        for cmd, desc in protection_commands:
            test_command(instrument, cmd, desc)
            
        # Try to discover what modes are available
        print("\nDiscovering Available Modes:")
        print("-" * 29)
        
        # Common modes to try setting (safely)
        safe_modes = [
            "CC",      # Constant Current
            "CV",      # Constant Voltage  
            "CP",      # Constant Power
            "CR",      # Constant Resistance
            "BATT",    # Battery
            "LED",     # LED
            "LIST",    # List
        ]
        
        for mode in safe_modes:
            print(f"Testing mode: {mode}")
            try:
                # Try different command formats
                formats = [f"FUNC {mode}", f"MODE {mode}", f"APPL {mode}"]
                
                for fmt in formats:
                    try:
                        instrument.write(fmt)
                        time.sleep(0.1)
                        
                        # Query back to see if it worked
                        try:
                            result = instrument.query("FUNC?").strip()
                            print(f"  {fmt} -> FUNC? = {result}")
                        except:
                            try:
                                result = instrument.query("MODE?").strip()
                                print(f"  {fmt} -> MODE? = {result}")
                            except:
                                print(f"  {fmt} -> Command sent (no query response)")
                        break
                        
                    except Exception as e:
                        continue
                        
            except Exception as e:
                print(f"  Error testing {mode}: {str(e)}")
            print()
        
        instrument.close()
        print("Discovery completed!")
        
    except Exception as e:
        print(f"Discovery error: {str(e)}")

def test_command(instrument, command, description):
    """Test a single command safely"""
    try:
        print(f"TESTING: {command} ({description})")
        
        if command.endswith('?'):
            # Query command
            response = instrument.query(command).strip()
            print(f"  RESPONSE: {response}")
        else:
            # Write command
            instrument.write(command)
            print(f"  SENT: {command}")
            time.sleep(0.1)
            
            # Try to verify the command worked
            if command.startswith('FUNC'):
                try:
                    verify = instrument.query("FUNC?").strip()
                    print(f"  VERIFY: FUNC? = {verify}")
                except:
                    pass
                    
    except Exception as e:
        print(f"  ERROR: {str(e)}")
    
    print()
    time.sleep(0.1)

def test_battery_setup():
    """Test setting up battery mode with typical parameters"""
    
    visa_address = "USB0::0x1AB1::0x0E11::DL3A231800370::INSTR"
    
    try:
        print("\nTesting Battery Mode Setup:")
        print("=" * 30)
        
        rm = pyvisa.ResourceManager()
        instrument = rm.open_resource(visa_address)
        instrument.timeout = 5000
        
        # Safe battery test setup sequence
        setup_commands = [
            ("LOAD OFF", "Ensure load is off"),
            ("*CLS", "Clear errors"),
            ("*RST", "Reset device"),
            ("FUNC CC", "Set constant current mode"),
            ("CURR:RANG LOW", "Set low current range"),
            ("CURR 1.0", "Set 1A current limit"),
            ("VOLT:PROT:LOW 2.5", "Set 2.5V cutoff"),
            ("VOLT:PROT:STAT ON", "Enable voltage protection"),
        ]
        
        for cmd, desc in setup_commands:
            try:
                print(f"SETUP: {cmd} ({desc})")
                instrument.write(cmd)
                time.sleep(0.2)
                print("  OK")
            except Exception as e:
                print(f"  ERROR: {str(e)}")
        
        # Query final state
        print("\nFinal State:")
        queries = [
            "FUNC?",
            "CURR?", 
            "VOLT:PROT:LOW?",
            "VOLT:PROT:STAT?",
            "CURR:RANG?",
            "MEAS:VOLT?",
            "MEAS:CURR?",
        ]
        
        for query in queries:
            try:
                result = instrument.query(query).strip()
                print(f"  {query} = {result}")
            except Exception as e:
                print(f"  {query} ERROR: {str(e)}")
        
        instrument.close()
        
    except Exception as e:
        print(f"Battery setup error: {str(e)}")

if __name__ == "__main__":
    print("DL3021 Battery Mode Discovery and Setup Test")
    print("This script will safely explore battery mode commands.")
    print("The load will be kept OFF during testing.")
    print()
    
    discover_battery_mode()
    test_battery_setup()
