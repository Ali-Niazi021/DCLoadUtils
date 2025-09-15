#!/usr/bin/env python3
"""
Simple Battery Current Test
Connects to Rigol DC Load via Raspberry Pi SCPI server and performs battery discharge test.
Server address: dcloadpi.local:5025

This program:
1. Sets up the DC Load in battery test mode
2. Configures current, voltage stop, and time stop parameters
3. Starts the test and logs voltage/current readings to CSV
4. Stops when any termination condition is met or Ctrl+C is pressed

Usage: python simple_battery_current_test.py
Exit: Press Ctrl+C
"""

import socket
import json
import time
import signal
import sys
import csv
import os
from datetime import datetime


# TEST CONFIGURATION
# ===================
# Set these values according to your test requirements
# If set to None, that parameter will be ignored/disabled

CURRENT_A = 1.0          # Discharge current in Amperes
V_STOP_V = 2.5           # Cut-off voltage in Volts (set to None to disable)
T_STOP_SEC = None         # Stop time in seconds (set to None to disable)

# Additional configuration
CURRENT_RANGE = "LOW"    # "LOW" or "HIGH" - use LOW for better accuracy at low currents
UPDATE_INTERVAL = 0.2    # Data logging interval in seconds
OUTPUT_DIR = "Output"    # Directory for CSV output files


class BatteryCurrentTest:
    def __init__(self, host="dcloadpi.local", port=5025):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.csv_file = None
        self.csv_writer = None
        self.start_time = None
        
        # Test configuration
        self.current_a = CURRENT_A
        self.v_stop_v = V_STOP_V
        self.t_stop_sec = T_STOP_SEC
        self.current_range = CURRENT_RANGE
        
    def connect(self):
        """Connect to the DC Load SCPI server"""
        try:
            print(f"Connecting to DC Load at {self.host}:{self.port}...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)  # 10 second timeout
            self.socket.connect((self.host, self.port))
            print("✓ Connected successfully!")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def send_command(self, command):
        """Send SCPI command and return parsed JSON response"""
        try:
            # Send command
            self.socket.send((command + '\n').encode('utf-8'))
            
            # Receive response
            response = self.socket.recv(4096).decode('utf-8').strip()
            return json.loads(response)
        except Exception as e:
            print(f"Command error: {e}")
            return None
    
    def get_instrument_info(self):
        """Get and display instrument identification"""
        response = self.send_command('*IDN?')
        if response and response.get('success'):
            print(f"Instrument: {response['response']}")
            return True
        else:
            print("Failed to get instrument identification")
            return False
    
    def setup_battery_mode(self):
        """Set up the DC Load for battery testing"""
        print("\nSetting up battery test mode...")
        
        # Ensure input is OFF before configuration
        print("• Turning input OFF for safe configuration...")
        response = self.send_command(':INP OFF')
        if not response or not response.get('success'):
            print("  ⚠ Warning: Could not turn input OFF")
        
        time.sleep(0.5)
        
        # Clear any errors
        print("• Clearing errors...")
        self.send_command('*CLS')
        
        # Set to battery mode
        print("• Setting function mode to battery...")
        response = self.send_command(':SOUR:FUNC:MODE BATT')
        if not response or not response.get('success'):
            print("  ⚠ Warning: Could not set battery mode directly")
            # Try alternative: set CC mode first, then battery mode
            print("  • Trying CC mode first...")
            self.send_command(':SOUR:FUNC CC')
            time.sleep(0.2)
            response = self.send_command(':SOUR:FUNC:MODE BATT')
            if not response or not response.get('success'):
                print("  ⚠ Warning: Battery mode setup failed, continuing with CC mode")
        
        # Set current range
        print(f"• Setting current range to {self.current_range}...")
        response = self.send_command(f':SOUR:CURR:RANG {self.current_range}')
        if not response or not response.get('success'):
            print("  ⚠ Warning: Could not set current range")
        
        # Set discharge current
        print(f"• Setting discharge current to {self.current_a}A...")
        response = self.send_command(f':SOUR:CURR {self.current_a}')
        if not response or not response.get('success'):
            print("  ✗ Error: Could not set discharge current")
            return False
        
        # Set voltage stop (cut-off voltage) if specified
        if self.v_stop_v is not None:
            print(f"• Setting voltage stop to {self.v_stop_v}V...")
            response = self.send_command(f':SOUR:VOLT:LIM {self.v_stop_v}')
            if not response or not response.get('success'):
                print("  ⚠ Warning: Could not set voltage limit")
        else:
            print("• Voltage stop: DISABLED (V_STOP_V = None)")
        
        # Note: Time stop is typically handled by the monitoring loop
        # as the DC load may not have a built-in time limit function
        if self.t_stop_sec is not None:
            print(f"• Time stop: {self.t_stop_sec} seconds (software controlled)")
        else:
            print("• Time stop: DISABLED (T_STOP_SEC = None)")
        
        time.sleep(0.5)
        
        # Verify configuration
        print("\n• Verifying configuration...")
        queries = [
            (':SOUR:FUNC?', 'Function'),
            (':SOUR:FUNC:MODE?', 'Function Mode'),
            (':SOUR:CURR?', 'Current Setting'),
            (':SOUR:CURR:RANG?', 'Current Range'),
            (':SOUR:VOLT:LIM?', 'Voltage Limit'),
        ]
        
        for query, desc in queries:
            response = self.send_command(query)
            if response and response.get('success'):
                print(f"  {desc}: {response['response']}")
            else:
                print(f"  {desc}: Query failed")
        
        print("✓ Battery mode setup completed")
        return True
    
    def read_measurements(self):
        """Read voltage and current measurements"""
        # Get voltage measurement
        volt_response = self.send_command(':MEAS:VOLT?')
        curr_response = self.send_command(':MEAS:CURR?')
        
        voltage = None
        current = None
        
        if volt_response and volt_response.get('success'):
            try:
                voltage = float(volt_response['response'])
            except (ValueError, TypeError):
                voltage = None
                
        if curr_response and curr_response.get('success'):
            try:
                current = float(curr_response['response'])
            except (ValueError, TypeError):
                current = None
                
        return voltage, current
    
    def setup_csv_logging(self):
        """Set up CSV file for data logging"""
        # Create output directory if it doesn't exist
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"battery_test_{timestamp}.csv"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        try:
            self.csv_file = open(filepath, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            
            # Write header
            header = [
                'Timestamp',
                'Elapsed_Time_s',
                'Voltage_V',
                'Current_A',
                'Power_W'
            ]
            self.csv_writer.writerow(header)
            self.csv_file.flush()
            
            print(f"✓ Logging to: {filepath}")
            return True
            
        except Exception as e:
            print(f"✗ Error setting up CSV logging: {e}")
            return False
    
    def log_data(self, voltage, current, elapsed_time):
        """Log data to CSV file"""
        if self.csv_writer is None:
            return
        
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            power = voltage * current if voltage is not None and current is not None else None
            
            row = [
                timestamp,
                f"{elapsed_time:.1f}",
                f"{voltage:.3f}" if voltage is not None else "---",
                f"{current:.3f}" if current is not None else "---",
                f"{power:.3f}" if power is not None else "---"
            ]
            
            self.csv_writer.writerow(row)
            self.csv_file.flush()
            
        except Exception as e:
            print(f"Error logging data: {e}")
    
    def check_stop_conditions(self, voltage, current, elapsed_time):
        """Check if any stop conditions are met"""
        # Check voltage stop condition
        if self.v_stop_v is not None and voltage is not None:
            if voltage <= self.v_stop_v:
                print(f"\n⚠ VOLTAGE STOP: {voltage:.3f}V ≤ {self.v_stop_v}V")
                return True
        
        # Check time stop condition
        if self.t_stop_sec is not None:
            if elapsed_time >= self.t_stop_sec:
                print(f"\n⏰ TIME STOP: {elapsed_time:.1f}s ≥ {self.t_stop_sec}s")
                return True
        
        return False
    
    def disconnect(self):
        """Disconnect from the server and clean up"""
        if self.socket:
            try:
                # Turn off the input before disconnecting
                self.send_command(':INP OFF')
                time.sleep(0.1)
                self.send_command('QUIT')
                self.socket.close()
                print("\n✓ Disconnected from DC Load")
            except:
                pass
        
        if self.csv_file:
            try:
                self.csv_file.close()
                print("✓ CSV file closed")
            except:
                pass
    
    def signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\nShutting down battery test...")
        self.running = False
        
        # Turn off the load
        try:
            if self.socket:
                print("Turning off DC Load input...")
                self.send_command(':INP OFF')
                time.sleep(0.2)
        except:
            pass
        
        self.disconnect()
        sys.exit(0)
    
    def run_test(self):
        """Run the battery discharge test"""
        # Set up signal handler for Ctrl+C
        signal.signal(signal.SIGINT, self.signal_handler)
        
        print("Battery Current Test v1.0")
        print("=" * 40)
        print(f"Current: {self.current_a}A")
        print(f"V-Stop: {self.v_stop_v}V" if self.v_stop_v is not None else "V-Stop: DISABLED")
        print(f"T-Stop: {self.t_stop_sec}s" if self.t_stop_sec is not None else "T-Stop: DISABLED")
        print(f"Range: {self.current_range}")
        print()
        
        # Connect to the device
        if not self.connect():
            return
        
        # Get instrument info
        if not self.get_instrument_info():
            self.disconnect()
            return
        
        # Set up battery mode
        if not self.setup_battery_mode():
            print("✗ Failed to set up battery mode")
            self.disconnect()
            return
        
        # Set up CSV logging
        if not self.setup_csv_logging():
            print("✗ Failed to set up CSV logging")
            self.disconnect()
            return
        
        # Start the test
        print("\n" + "=" * 60)
        print("STARTING BATTERY TEST")
        print("Press Ctrl+C to stop the test")
        print("=" * 60)
        
        # Turn on the input to start the test
        print("Turning ON DC Load input...")
        response = self.send_command(':INP ON')
        if not response or not response.get('success'):
            print("✗ Failed to turn on input")
            self.disconnect()
            return
        
        print("✓ Input ON - Test started!")
        print()
        print(f"{'Elapsed':<12} {'Voltage':<9} {'Current':<9} {'Power':<9}")
        print(f"{'(mm:ss.zzz)':<12} {'(V)':<9} {'(A)':<9} {'(W)':<9}")
        print("-" * 50)
        
        self.running = True
        self.start_time = time.time()
        
        try:
            while self.running:
                current_time = time.time()
                elapsed_time = current_time - self.start_time
                
                # Read measurements
                voltage, current = self.read_measurements()
                
                # Check stop conditions
                if self.check_stop_conditions(voltage, current, elapsed_time):
                    self.running = False
                    break
                
                # Calculate power
                power = None
                if voltage is not None and current is not None:
                    power = voltage * current
                
                # Format and display readings
                # Convert elapsed time to mm:ss.zzz format
                minutes = int(elapsed_time // 60)
                seconds = elapsed_time % 60
                time_str = f"{minutes:02d}:{seconds:06.3f}"
                volt_str = f"{voltage:.3f}" if voltage is not None else "---"
                curr_str = f"{current:.3f}" if current is not None else "---"
                power_str = f"{power:.3f}" if power is not None else "---"
                
                print(f"{time_str:<12} {volt_str:<9} {curr_str:<9} {power_str:<9}")
                
                # Log data to CSV
                self.log_data(voltage, current, elapsed_time)
                
                # Wait for next update
                time.sleep(UPDATE_INTERVAL)
                
        except KeyboardInterrupt:
            # This should be caught by signal handler, but just in case
            pass
        except Exception as e:
            print(f"\nError during test: {e}")
        finally:
            # Turn off the load and disconnect
            print("\nStopping test...")
            try:
                self.send_command(':INP OFF')
                print("✓ Input turned OFF")
            except:
                pass
            
            self.disconnect()
            print("✓ Test completed")


def main():
    """Main function"""
    # Validate configuration
    if CURRENT_A is None or CURRENT_A <= 0:
        print("✗ Error: CURRENT_A must be set to a positive value")
        return
    
    if V_STOP_V is not None and V_STOP_V <= 0:
        print("✗ Error: V_STOP_V must be positive or None")
        return
    
    if T_STOP_SEC is not None and T_STOP_SEC <= 0:
        print("✗ Error: T_STOP_SEC must be positive or None")
        return
    
    # Create and run test
    test = BatteryCurrentTest()
    test.run_test()


if __name__ == "__main__":
    main()