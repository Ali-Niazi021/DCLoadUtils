#!/usr/bin/env python3
"""
Simple DC Load Monitor
Connects to Rigol DC Load via Raspberry Pi SCPI server and displays real-time voltage and current readings.
Server address: dcloadpi.local:5025

Usage: python simple_monitor.py
Exit: Press Ctrl+C
"""

import socket
import json
import time
import signal
import sys
from datetime import datetime


class DCLoadMonitor:
    def __init__(self, host="dcloadpi.local", port=5025):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        
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
    
    def disconnect(self):
        """Disconnect from the server"""
        if self.socket:
            try:
                self.send_command('QUIT')
                self.socket.close()
                print("\n✓ Disconnected from DC Load")
            except:
                pass
    
    def signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\nShutting down monitor...")
        self.running = False
        self.disconnect()
        sys.exit(0)
    
    def start_monitoring(self, update_interval=1.0):
        """Start the monitoring loop"""
        # Set up signal handler for Ctrl+C
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # Connect to the device
        if not self.connect():
            return
        
        # Get instrument info
        if not self.get_instrument_info():
            self.disconnect()
            return
        
        print(f"\nStarting real-time monitoring (update every {update_interval}s)")
        print("Press Ctrl+C to exit\n")
        print("=" * 60)
        print(f"{'Time':<12} {'Voltage (V)':<12} {'Current (A)':<12} {'Power (W)':<12}")
        print("=" * 60)
        
        self.running = True
        
        try:
            while self.running:
                # Get current time
                current_time = datetime.now().strftime("%H:%M:%S")
                
                # Read measurements
                voltage, current = self.read_measurements()
                
                # Calculate power if both readings are valid
                power = None
                if voltage is not None and current is not None:
                    power = voltage * current
                
                # Format and display readings
                volt_str = f"{voltage:.3f}" if voltage is not None else "---"
                curr_str = f"{current:.3f}" if current is not None else "---"
                power_str = f"{power:.3f}" if power is not None else "---"
                
                print(f"{current_time:<12} {volt_str:<12} {curr_str:<12} {power_str:<12}")
                
                # Wait for next update
                time.sleep(update_interval)
                
        except KeyboardInterrupt:
            # This should be caught by signal handler, but just in case
            pass
        except Exception as e:
            print(f"\nError during monitoring: {e}")
        finally:
            self.disconnect()


def main():
    """Main function"""
    print("DC Load Monitor v1.0")
    print("===================")
    
    # Create and start monitor
    monitor = DCLoadMonitor()
    monitor.start_monitoring(update_interval=0.2)  # Update every 1 second


if __name__ == "__main__":
    main()