#!/usr/bin/env python3
"""
Endurance Test Automation Script

This script automates battery cell testing using telemetry data from a car's endurance event.
It reads current data from CSV, converts it for single cell testing, and controls the DC load
accordingly while monitoring voltage for cutoff conditions.

Features:
- Reads CSV telemetry data (100Hz sampling)
- Converts negative current to positive load current
- Divides by 3 for single cell representation
- Clamps current to 0-40A range
- Uses battery mode on DC load
- Monitors voltage cutoff at 2.75V
- Simple DearPyGUI interface
"""

import dearpygui.dearpygui as dpg
import pyvisa
import pandas as pd
import threading
import time
import os
import csv
import numpy as np
from datetime import datetime, timedelta
from collections import deque

class EnduranceTestController:
    def __init__(self):
        # VISA settings
        self.visa_address = "USB0::0x1AB1::0x0E11::DL3A231800370::INSTR"
        self.rm = None
        self.instrument = None
        self.is_connected = False
        
        # VISA communication control
        self.last_measurement_time = 0
        self.measurement_interval = 2.0  # Minimum 2s between measurements
        self.last_command_time = 0
        self.command_interval = 0.3  # Minimum 0.3s between commands
        self.max_retries = 3  # Maximum retry attempts for commands
        
        # Cached measurements to handle timeouts
        self.last_valid_voltage = 3.7  # Start with safe voltage
        self.last_valid_current = 0.0
        self.last_measurement_success_time = None
        self.measurement_timeout_threshold = 10.0  # Consider data stale after 10s
        
        # Test settings
        self.csv_file = None
        self.test_data = None
        self.test_running = False
        self.test_paused = False
        self.current_row = 0
        self.start_time = None
        
        # Current interpolation settings
        self.interpolation_method = "rms"  # "average", "rms", "weighted_avg", "peak_aware", "energy_equiv"
        
        # Safety limits
        self.voltage_cutoff = 2.75  # Volts
        self.max_current = 40.0     # Amps
        self.min_current = 0.0      # Amps
        
        # Current readings
        self.current_voltage = 0.0
        self.current_current = 0.0
        self.target_current = 0.0
        self.test_progress = 0.0
        
        # Voltage cutoff buffer
        self.voltage_below_cutoff_time = None
        self.voltage_cutoff_buffer = 1.0  # 1 second buffer
        
        # Threading
        self.test_thread = None
        self.monitor_thread = None
        self.stop_event = threading.Event()
        
        # Logging
        self.log_messages = []
        self.test_log = []
        self.csv_logger = None
        self.csv_log_file = None
        
        # Plot data for live chart
        self.plot_voltage = deque(maxlen=300)  # Last 5 minutes at 1Hz
        self.plot_current = deque(maxlen=300)
        self.plot_time = deque(maxlen=300)
        
    def setup_gui(self):
        """Setup DearPyGUI interface"""
        dpg.create_context()
        
        # Create a theme with larger fonts
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 12)
        
        # Create larger font
        with dpg.font_registry():
            # Load default font with larger size
            large_font = dpg.add_font("c:/windows/fonts/segoeui.ttf", 18)
            medium_font = dpg.add_font("c:/windows/fonts/segoeui.ttf", 16)
        
        dpg.bind_theme(global_theme)
        
        # Main window
        with dpg.window(label="Endurance Test Controller", tag="main_window"):
            
            # Connection section
            with dpg.group(horizontal=True):
                dpg.add_text("DC Load Status:", color=(200, 200, 200))
                dpg.add_text("Disconnected", tag="connection_status", color=(255, 100, 100))
                dpg.add_button(label="Connect", callback=self.toggle_connection, tag="connect_btn", width=120, height=35)
            
            dpg.add_separator()
            
            # File selection
            with dpg.group(horizontal=True):
                dpg.add_text("CSV File:", color=(200, 200, 200))
                dpg.add_input_text(tag="csv_path", width=450, readonly=True)
                dpg.add_button(label="Browse", callback=self.browse_csv_file, width=100, height=30)
            
            # Interpolation method selection
            with dpg.group(horizontal=True):
                dpg.add_text("Current Interpolation:", color=(200, 200, 200))
                dpg.add_combo(["Average", "RMS (Root Mean Square)", "Weighted Average", "Peak Aware", "Energy Equivalent"], 
                             default_value="RMS (Root Mean Square)", tag="interpolation_combo", width=250,
                             callback=self.on_interpolation_change)
            
            dpg.add_separator()
            
            # Current readings display
            with dpg.group():
                dpg.add_text("Real-time Readings", color=(100, 255, 100))
                
                with dpg.group(horizontal=True):
                    dpg.add_text("Voltage:", color=(200, 200, 200))
                    dpg.add_text("0.000 V", tag="voltage_display", color=(100, 150, 255))
                    
                with dpg.group(horizontal=True):
                    dpg.add_text("Current:", color=(200, 200, 200))
                    dpg.add_text("0.000 A", tag="current_display", color=(255, 150, 100))
                    
                with dpg.group(horizontal=True):
                    dpg.add_text("Target Current:", color=(200, 200, 200))
                    dpg.add_text("0.000 A", tag="target_current_display", color=(150, 255, 150))
            
            dpg.add_separator()
            
            # Test progress
            with dpg.group():
                dpg.add_text("Test Progress", color=(255, 255, 100))
                dpg.add_progress_bar(tag="progress_bar", width=450, height=25)
                
                with dpg.group(horizontal=True):
                    dpg.add_text("Row:", color=(200, 200, 200))
                    dpg.add_text("0 / 0", tag="row_progress")
                    
                with dpg.group(horizontal=True):
                    dpg.add_text("Time:", color=(200, 200, 200))
                    dpg.add_text("00:00:00", tag="time_progress")
            
            dpg.add_separator()
            
            # Live plot
            with dpg.group():
                dpg.add_text("Live Data Plot", color=(100, 255, 100))
                
                with dpg.plot(label="Voltage & Current vs Time", height=250, width=650):
                    dpg.add_plot_legend()
                    dpg.add_plot_axis(dpg.mvXAxis, label="Time (seconds)", tag="x_axis")
                    dpg.add_plot_axis(dpg.mvYAxis, label="Voltage (V)", tag="y_axis_voltage")
                    dpg.add_plot_axis(dpg.mvYAxis, label="Current (A)", tag="y_axis_current")
                    
                    # Voltage line (left Y axis)
                    dpg.add_line_series([], [], label="Voltage", parent="y_axis_voltage", tag="voltage_series")
                    
                    # Current line (right Y axis) 
                    dpg.add_line_series([], [], label="Current", parent="y_axis_current", tag="current_series")
            
            dpg.add_separator()
            
            # Test controls
            with dpg.group():
                dpg.add_text("Test Controls", color=(255, 255, 100))
                
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Start Test", callback=self.start_test, tag="start_btn", width=120, height=40)
                    dpg.add_button(label="Stop Test", callback=self.stop_test, tag="stop_btn", width=120, height=40, enabled=False)
                    dpg.add_button(label="Emergency Stop", callback=self.emergency_stop, tag="emergency_btn", width=140, height=40)
                
                with dpg.group(horizontal=True):
                    dpg.add_text("Voltage Cutoff:", color=(200, 200, 200))
                    dpg.add_input_float(tag="voltage_cutoff_input", default_value=2.75, 
                                      width=100, step=0.01, format="%.3f")
                    dpg.add_text("V", color=(200, 200, 200))
            
            dpg.add_separator()
            
            # Safety status
            with dpg.group():
                dpg.add_text("Safety Status", color=(255, 255, 100))
                dpg.add_text("Load OFF", tag="load_status", color=(100, 255, 100))
                dpg.add_text("Voltage OK", tag="voltage_status", color=(100, 255, 100))
            
            dpg.add_separator()
            
            # Log display
            with dpg.group():
                dpg.add_text("Log Messages", color=(255, 255, 100))
                dpg.add_child_window(tag="log_window", height=180, width=700)
        
        # Setup viewport
        dpg.create_viewport(title="Endurance Test Controller", width=750, height=1000)
        dpg.setup_dearpygui()
        dpg.set_primary_window("main_window", True)
        
        # Bind the large font to the main window
        dpg.bind_font(large_font)
        
        # Start monitor thread
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self.log_message("GUI initialized")
        
    def log_message(self, message):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_messages.append(log_entry)
        
        # Keep only last 50 messages
        if len(self.log_messages) > 50:
            self.log_messages.pop(0)
        
        # Update GUI log (if available)
        try:
            # Check if GUI is ready before updating
            if dpg.does_item_exist("log_window"):
                dpg.delete_item("log_window", children_only=True)
                for msg in self.log_messages[-10:]:  # Show last 10 messages
                    dpg.add_text(msg, parent="log_window")
        except Exception as e:
            # Silently ignore GUI update errors to prevent popups
            pass
            
        print(log_entry)  # Also print to console
        
    def on_interpolation_change(self, sender, app_data):
        """Handle interpolation method change"""
        method_map = {
            "Average": "average",
            "RMS (Root Mean Square)": "rms", 
            "Weighted Average": "weighted_avg",
            "Peak Aware": "peak_aware",
            "Energy Equivalent": "energy_equiv"
        }
        self.interpolation_method = method_map.get(app_data, "rms")
        self.log_message(f"Interpolation method changed to: {app_data}")
        
    def interpolate_current_window(self, current_slice):
        """Interpolate current from 200-row window using selected method"""
        if len(current_slice) == 0:
            return 0.0
            
        # Process current: negative -> positive, divide by 3, clamp
        processed_currents = []
        for raw_current in current_slice:
            if raw_current < 0:
                processed_current = abs(raw_current) / 3.0
            else:
                processed_current = 0.0
            # Clamp to valid range
            processed_current = max(self.min_current, min(self.max_current, processed_current))
            processed_currents.append(processed_current)
        
        if not processed_currents:
            return 0.0
            
        currents = np.array(processed_currents)
        
        if self.interpolation_method == "average":
            # Simple arithmetic mean
            return float(np.mean(currents))
            
        elif self.interpolation_method == "rms":
            # Root Mean Square - better for power/energy representation
            return float(np.sqrt(np.mean(currents**2)))
            
        elif self.interpolation_method == "weighted_avg":
            # Weighted average giving more importance to higher currents
            weights = currents / np.sum(currents) if np.sum(currents) > 0 else np.ones_like(currents)
            return float(np.average(currents, weights=weights))
            
        elif self.interpolation_method == "peak_aware":
            # Combination of average and peak, weighted toward peaks
            avg_current = np.mean(currents)
            max_current = np.max(currents)
            # Weight: 70% average, 30% peak
            return float(0.7 * avg_current + 0.3 * max_current)
            
        elif self.interpolation_method == "energy_equiv":
            # Energy equivalent current (I²t based)
            # This represents the current that would produce the same energy over the time period
            if len(currents) > 0:
                # Calculate energy (I²t) and find equivalent constant current
                energy_sum = np.sum(currents**2)
                return float(np.sqrt(energy_sum / len(currents)))
            else:
                return 0.0
        else:
            # Default to RMS
            return float(np.sqrt(np.mean(currents**2)))
        
    def safe_write(self, command):
        """Safely write command to instrument with timing control and retries"""
        if not self.instrument:
            return False
            
        for attempt in range(self.max_retries):
            try:
                current_time = time.time()
                if current_time - self.last_command_time < self.command_interval:
                    time.sleep(self.command_interval - (current_time - self.last_command_time))
                
                self.instrument.write(command)
                self.last_command_time = time.time()
                return True
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    self.log_message(f"Write retry {attempt + 1}/{self.max_retries} for '{command}': {str(e)}")
                    time.sleep(0.5 * (attempt + 1))  # Increasing delay between retries
                    continue
                else:
                    self.log_message(f"Write failed after {self.max_retries} attempts for '{command}': {str(e)}")
                    return False
        return False
            
    def safe_query(self, command):
        """Safely query instrument with timing control and retries"""
        if not self.instrument:
            return None
            
        for attempt in range(self.max_retries):
            try:
                current_time = time.time()
                if current_time - self.last_command_time < self.command_interval:
                    time.sleep(self.command_interval - (current_time - self.last_command_time))
                
                result = self.instrument.query(command).strip()
                self.last_command_time = time.time()
                return result
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    self.log_message(f"Query retry {attempt + 1}/{self.max_retries} for '{command}': {str(e)}")
                    time.sleep(0.5 * (attempt + 1))  # Increasing delay between retries
                    continue
                else:
                    self.log_message(f"Query failed after {self.max_retries} attempts for '{command}': {str(e)}")
                    return None
        return None
            
    def safe_measure(self):
        """Safely measure voltage and current with timeout protection"""
        if not self.instrument:
            return self.last_valid_voltage, self.last_valid_current
            
        current_time = time.time()
        if current_time - self.last_measurement_time < self.measurement_interval:
            return self.last_valid_voltage, self.last_valid_current  # Return cached values
            
        # Try to get fresh measurements with aggressive timeout handling
        try:
            # Use very long timeout for individual queries but overall timeout protection
            start_time = time.time()
            
            # Try voltage measurement
            voltage = None
            for attempt in range(2):  # Only 2 attempts for measurements
                try:
                    voltage_str = self.instrument.query(":MEAS:VOLT?").strip()
                    voltage = float(voltage_str)
                    break
                except Exception as e:
                    if attempt == 0:
                        self.log_message(f"Voltage measurement retry: {str(e)}")
                        time.sleep(0.5)
                    else:
                        self.log_message(f"Voltage measurement failed: {str(e)}")
                        voltage = None
                        
            # Check overall timeout
            if time.time() - start_time > 5.0:  # Don't spend more than 5s on measurements
                self.log_message("Measurement taking too long, using cached values")
                return self.last_valid_voltage, self.last_valid_current
                
            # Try current measurement
            current = None
            for attempt in range(2):  # Only 2 attempts for measurements
                try:
                    current_str = self.instrument.query(":MEAS:CURR?").strip()
                    current = float(current_str)
                    break
                except Exception as e:
                    if attempt == 0:
                        self.log_message(f"Current measurement retry: {str(e)}")
                        time.sleep(0.5)
                    else:
                        self.log_message(f"Current measurement failed: {str(e)}")
                        current = None
                        
            # Update cached values if we got valid readings
            if voltage is not None and current is not None:
                # Sanity check the readings
                if 0.0 <= voltage <= 50.0 and 0.0 <= current <= 50.0:
                    self.last_valid_voltage = voltage
                    self.last_valid_current = current
                    self.last_measurement_success_time = datetime.now()
                    self.last_measurement_time = time.time()
                    return voltage, current
                else:
                    self.log_message(f"Invalid readings: V={voltage}, I={current} - using cached values")
            
            # If we got here, measurements failed - return cached values
            return self.last_valid_voltage, self.last_valid_current
            
        except Exception as e:
            self.log_message(f"Measurement error: {str(e)} - using cached values")
            return self.last_valid_voltage, self.last_valid_current
            
    def safe_set_current(self, current_value):
        """Safely set current with extra resilience for critical operations"""
        if not self.instrument:
            return False
            
        command = f":SOUR:CURR:LEV {current_value:.3f}"
        
        # Extra retry attempts for current setting since it's critical
        for attempt in range(5):  # More retries for current setting
            try:
                # Longer delay before current setting
                time.sleep(0.3)
                
                # Clear any pending errors first
                if attempt > 0:
                    try:
                        self.instrument.write("*CLS")
                        time.sleep(0.1)
                    except:
                        pass
                
                # Set the current
                self.instrument.write(command)
                time.sleep(0.2)  # Give time for command to process
                
                # Verify the setting took effect
                try:
                    verify_cmd = ":SOUR:CURR:LEV?"
                    time.sleep(0.1)
                    result = self.instrument.query(verify_cmd).strip()
                    set_current = float(result)
                    
                    # Check if value is close enough (within 1% or 0.01A)
                    tolerance = max(0.01, abs(current_value * 0.01))
                    if abs(set_current - current_value) <= tolerance:
                        self.log_message(f"Current set successfully: {current_value:.3f}A (verified: {set_current:.3f}A)")
                        return True
                    else:
                        self.log_message(f"Current verification failed: wanted {current_value:.3f}A, got {set_current:.3f}A")
                        
                except Exception as verify_error:
                    self.log_message(f"Current verification error: {str(verify_error)}")
                    # Continue anyway if verification fails but setting seemed to work
                    return True
                    
            except Exception as e:
                error_msg = str(e)
                if attempt < 4:
                    wait_time = 1.0 * (attempt + 1)  # Increasing wait time
                    self.log_message(f"Current setting retry {attempt + 1}/5: {error_msg} (waiting {wait_time}s)")
                    time.sleep(wait_time)
                    continue
                else:
                    self.log_message(f"Current setting failed after 5 attempts: {error_msg}")
                    return False
                    
        return False
        
    def browse_csv_file(self):
        """Browse for CSV file"""
        def file_callback(sender, app_data):
            if app_data and 'file_path_name' in app_data and app_data['file_path_name']:
                file_path = app_data['file_path_name']
                dpg.set_value("csv_path", file_path)
                self.load_csv_file(file_path)
        
        # Use a unique tag each time to avoid conflicts
        dialog_tag = f"file_dialog_{int(time.time())}"
        
        with dpg.file_dialog(directory_selector=False, show=True, callback=file_callback,
                           tag=dialog_tag, width=700, height=400, modal=True):
            dpg.add_file_extension(".*", color=(255, 255, 255, 255))
            dpg.add_file_extension(".csv", color=(0, 255, 0, 255))
            
    def load_csv_file(self, file_path):
        """Load and validate CSV file"""
        try:
            self.log_message(f"Loading CSV file: {os.path.basename(file_path)}")
            
            # Load CSV data
            self.test_data = pd.read_csv(file_path)
            self.csv_file = file_path
            
            # Validate data structure
            if len(self.test_data.columns) < 3:
                raise ValueError("CSV must have at least 3 columns")
            
            # Get current column (column C = index 2)
            current_column = self.test_data.iloc[:, 2]  # Column C (0-indexed as 2)
            
            # Check for numeric data
            if not pd.api.types.is_numeric_dtype(current_column):
                raise ValueError("Current column (C) must contain numeric data")
            
            rows = len(self.test_data)
            duration_seconds = rows / 100  # 100Hz sampling
            # Calculate actual test duration with 2-second updates
            test_duration_seconds = (rows / 200) * 2  # Every 200 rows = 2 seconds
            duration_str = str(timedelta(seconds=int(duration_seconds)))
            test_duration_str = str(timedelta(seconds=int(test_duration_seconds)))
            
            self.log_message(f"Loaded {rows} rows ({duration_str} recorded duration)")
            self.log_message(f"Test will take approximately {test_duration_str} (2-second updates)")
            self.log_message(f"Current range: {current_column.min():.3f} to {current_column.max():.3f}A")
            
            # Reset test position
            self.current_row = 0
            
        except Exception as e:
            self.log_message(f"Error loading CSV: {str(e)}")
            self.test_data = None
            self.csv_file = None
            
    def toggle_connection(self):
        """Connect/disconnect to DC load"""
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()
            
    def connect(self):
        """Connect to DC load"""
        try:
            self.log_message("Connecting to DC Load...")
            
            # Initialize VISA
            self.rm = pyvisa.ResourceManager()
            self.instrument = self.rm.open_resource(self.visa_address)
            self.instrument.timeout = 30000  # Increase timeout to 30 seconds
            self.instrument.read_termination = '\n'
            self.instrument.write_termination = '\n'
            
            # Add delay after opening connection
            time.sleep(1.0)
            
            # Test connection
            idn = self.instrument.query("*IDN?").strip()
            self.log_message(f"Connected: {idn}")
            
            # Setup battery mode
            self.setup_battery_mode()
            
            self.is_connected = True
            dpg.set_value("connection_status", "Connected")
            dpg.configure_item("connection_status", color=(100, 255, 100))
            dpg.set_item_label("connect_btn", "Disconnect")
            
        except Exception as e:
            self.log_message(f"Connection failed: {str(e)}")
            if self.instrument:
                try:
                    self.instrument.close()
                except:
                    pass
                self.instrument = None
            if self.rm:
                try:
                    self.rm.close()
                except:
                    pass
                self.rm = None
                
    def disconnect(self):
        """Disconnect from DC load"""
        try:
            if self.test_running:
                self.stop_test()
                
            if self.instrument:
                # Safety: turn off load
                self.safe_write(":SOUR:INP OFF")
                time.sleep(0.5)  # Give time for command to execute
                
                try:
                    self.instrument.close()
                except Exception as e:
                    self.log_message(f"Instrument close error: {str(e)}")
                    
            if self.rm:
                try:
                    self.rm.close()
                except Exception as e:
                    self.log_message(f"Resource manager close error: {str(e)}")
                    
            self.is_connected = False
            self.instrument = None
            self.rm = None
            
            dpg.set_value("connection_status", "Disconnected")
            dpg.configure_item("connection_status", color=(255, 100, 100))
            dpg.set_item_label("connect_btn", "Connect")
            
            self.log_message("Disconnected from DC Load")
            
        except Exception as e:
            self.log_message(f"Disconnect error: {str(e)}")
            
    def setup_battery_mode(self):
        """Setup DC load in battery mode"""
        if not self.instrument:
            raise Exception("No instrument connection")
            
        try:
            self.log_message("Setting up battery mode...")
            
            # Safety first
            self.safe_write(":SOUR:INP OFF")
            time.sleep(0.5)
            
            # Clear errors
            self.safe_write("*CLS")
            time.sleep(0.3)
            
            # Set constant current function
            self.safe_write(":SOUR:FUNC CURR")
            time.sleep(0.3)
            
            # Enable battery mode
            self.safe_write(":SOUR:FUNC:MODE BATT")
            time.sleep(0.3)
            
            # Set low current range for better precision
            self.safe_write(":SOUR:CURR:RANG LOW")
            time.sleep(0.3)
            
            # Set initial current to 0
            success = self.safe_set_current(0.0)
            if not success:
                self.log_message("Warning: Failed to set initial current to 0")
            time.sleep(0.3)
            
            # Verify setup
            func = self.safe_query(":SOUR:FUNC?")
            mode = self.safe_query(":SOUR:FUNC:MODE?")
            
            self.log_message(f"Battery mode setup: Function={func}, Mode={mode}")
            
        except Exception as e:
            self.log_message(f"Battery mode setup error: {str(e)}")
            raise
            
    def start_test(self):
        """Start endurance test"""
        if not self.is_connected:
            self.log_message("Error: Not connected to DC load")
            return
            
        if not self.test_data is not None:
            self.log_message("Error: No CSV data loaded")
            return
            
        if self.test_running:
            self.log_message("Test already running")
            return
            
        try:
            self.log_message("Starting endurance test...")
            
            # Update voltage cutoff from GUI
            self.voltage_cutoff = dpg.get_value("voltage_cutoff_input")
            
            # Reset test state
            self.current_row = 0
            self.start_time = datetime.now()
            self.test_running = True
            self.stop_event.clear()
            
            # Setup CSV logging
            timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
            self.csv_log_file = f"endurance_test_log_{timestamp}.csv"
            
            # Create CSV logger
            with open(self.csv_log_file, 'w', newline='') as csvfile:
                fieldnames = ['timestamp', 'elapsed_seconds', 'row', 'target_current', 'measured_voltage', 'measured_current']
                self.csv_logger = csv.DictWriter(csvfile, fieldnames=fieldnames)
                self.csv_logger.writeheader()
            
            # Clear plot data
            self.plot_voltage.clear()
            self.plot_current.clear() 
            self.plot_time.clear()
            
            # Reset voltage cutoff buffer
            self.voltage_below_cutoff_time = None
            
            # Update GUI
            dpg.configure_item("start_btn", enabled=False)
            dpg.configure_item("stop_btn", enabled=True)
            
            # Start test thread
            self.test_thread = threading.Thread(target=self.test_loop, daemon=True)
            self.test_thread.start()
            
            self.log_message(f"Test started with {len(self.test_data)} data points")
            self.log_message(f"Voltage cutoff: {self.voltage_cutoff}V")
            self.log_message(f"Logging to: {self.csv_log_file}")
            
        except Exception as e:
            self.log_message(f"Test start error: {str(e)}")
            self.test_running = False
            
    def stop_test(self):
        """Stop endurance test"""
        if not self.test_running:
            return
            
        self.log_message("Stopping test...")
        self.test_running = False
        self.stop_event.set()
        
        # Turn off load
        try:
            if self.instrument:
                self.safe_write(":SOUR:INP OFF")
                time.sleep(0.2)  # Give time for command to execute
        except:
            pass
            
        # Update GUI
        dpg.configure_item("start_btn", enabled=True)
        dpg.configure_item("stop_btn", enabled=False)
        
    def emergency_stop(self):
        """Emergency stop - immediately turn off load"""
        self.log_message("EMERGENCY STOP ACTIVATED!")
        
        try:
            if self.instrument:
                self.instrument.write(":SOUR:INP OFF")
                
            self.stop_test()
            
        except Exception as e:
            self.log_message(f"Emergency stop error: {str(e)}")
            
    def test_loop(self):
        """Main test execution loop"""
        try:
            total_rows = len(self.test_data)
            
            while self.test_running and self.current_row < total_rows:
                if self.stop_event.is_set():
                    break
                    
                # Only update current every 200 rows (2 seconds of data)
                if self.current_row % 200 == 0:
                    # Get current data slice for next 200 rows
                    end_row = min(self.current_row + 200, total_rows)
                    current_slice = self.test_data.iloc[self.current_row:end_row, 2]  # Column C
                    
                    # Use selected interpolation method to calculate representative current
                    avg_current = self.interpolate_current_window(current_slice)
                    
                    # Set target current
                    self.target_current = avg_current
                    
                    # Log interpolation info occasionally
                    if self.current_row % 2000 == 0:
                        slice_min = np.min(np.abs(current_slice.values)) / 3.0
                        slice_max = np.min([np.max(np.abs(current_slice.values)) / 3.0, self.max_current])
                        slice_avg = np.mean(np.abs(current_slice.values)) / 3.0
                        self.log_message(f"Window {self.current_row}-{end_row}: Raw range {slice_min:.3f}-{slice_max:.3f}A (avg: {slice_avg:.3f}A), {self.interpolation_method}: {avg_current:.3f}A")
                    
                    # Update DC load with resilient current setting
                    try:
                        if avg_current > 0.001:  # Minimum threshold
                            success = self.safe_set_current(avg_current)
                            if not success:
                                self.log_message("Failed to set current level - continuing test")
                                # Don't break, just log and continue
                                
                            if self.current_row == 0 and success:  # Turn on load at first successful current setting
                                time.sleep(0.2)  # Small delay before turning on
                                load_success = self.safe_write(":SOUR:INP ON")
                                if not load_success:
                                    self.log_message("Failed to turn on load")
                                    break
                        else:
                            success = self.safe_set_current(0.0)
                            if not success:
                                self.log_message("Failed to set zero current - continuing test")
                            
                    except Exception as e:
                        self.log_message(f"Load control error: {str(e)} - continuing test")
                        # Don't break on current setting errors, just continue
                    
                    # Read measurements with safe timing
                    voltage, current = self.safe_measure()
                    
                    # Always log the measurements we have (even if cached)
                    elapsed_seconds = (datetime.now() - self.start_time).total_seconds()
                    log_data = {
                        'timestamp': datetime.now().isoformat(),
                        'elapsed_seconds': f"{elapsed_seconds:.1f}",
                        'row': self.current_row,
                        'target_current': f"{avg_current:.3f}",
                        'measured_voltage': f"{voltage:.3f}",
                        'measured_current': f"{current:.3f}"
                    }
                    
                    # Write to CSV file
                    try:
                        with open(self.csv_log_file, 'a', newline='') as csvfile:
                            fieldnames = ['timestamp', 'elapsed_seconds', 'row', 'target_current', 'measured_voltage', 'measured_current']
                            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                            writer.writerow(log_data)
                    except Exception as e:
                        self.log_message(f"CSV logging error: {str(e)}")
                    
                    # Update plot data
                    self.plot_time.append(elapsed_seconds)
                    self.plot_voltage.append(voltage)
                    self.plot_current.append(current)
                    
                    # Only check voltage cutoff if we have recent, valid measurements
                    measurement_age = None
                    if self.last_measurement_success_time:
                        measurement_age = (datetime.now() - self.last_measurement_success_time).total_seconds()
                    
                    # Only apply voltage cutoff if measurements are fresh (within last 10 seconds)
                    if measurement_age is not None and measurement_age <= self.measurement_timeout_threshold:
                        # Check voltage safety with 1-second buffer
                        current_time = datetime.now()
                        if voltage <= self.voltage_cutoff:
                            if self.voltage_below_cutoff_time is None:
                                # First time voltage dropped below cutoff
                                self.voltage_below_cutoff_time = current_time
                                self.log_message(f"Warning: Voltage below cutoff ({voltage:.3f}V <= {self.voltage_cutoff}V) - Starting 1s buffer (measurement age: {measurement_age:.1f}s)")
                            else:
                                # Check if voltage has been below cutoff for buffer duration
                                time_below = (current_time - self.voltage_below_cutoff_time).total_seconds()
                                if time_below >= self.voltage_cutoff_buffer:
                                    self.log_message(f"Voltage cutoff triggered: {voltage:.3f}V <= {self.voltage_cutoff}V for {time_below:.1f}s (measurement age: {measurement_age:.1f}s)")
                                    break
                        else:
                            # Voltage is above cutoff, reset buffer
                            if self.voltage_below_cutoff_time is not None:
                                self.log_message(f"Voltage recovered: {voltage:.3f}V > {self.voltage_cutoff}V")
                            self.voltage_below_cutoff_time = None
                    else:
                        # Measurements are too old - don't apply voltage cutoff
                        if measurement_age is not None:
                            if measurement_age > self.measurement_timeout_threshold:
                                # Reset voltage cutoff buffer if measurements are stale
                                if self.voltage_below_cutoff_time is not None:
                                    self.log_message(f"Ignoring voltage cutoff - measurements too old ({measurement_age:.1f}s)")
                                    self.voltage_below_cutoff_time = None
                
                # Update progress
                self.current_row += 1
                self.test_progress = self.current_row / total_rows
                
                # Log progress every 2000 rows (20 seconds)
                if self.current_row % 2000 == 0:
                    elapsed = datetime.now() - self.start_time
                    remaining_rows = total_rows - self.current_row
                    eta_seconds = (remaining_rows / 200) * 2  # Estimate based on 2-second updates
                    eta_str = str(timedelta(seconds=int(eta_seconds)))
                    self.log_message(f"Progress: {self.current_row}/{total_rows} ({self.test_progress*100:.1f}%) - Elapsed: {str(elapsed).split('.')[0]}, ETA: {eta_str}")
                
                # Sleep for 2 seconds every 200 rows to maintain timing
                if self.current_row % 200 == 0:
                    time.sleep(2.0)
                
            # Test completed
            self.test_running = False
            
            # Turn off load
            try:
                self.safe_write(":SOUR:INP OFF")
                time.sleep(0.2)
            except:
                pass
                
            if self.current_row >= total_rows:
                self.log_message("Endurance test completed successfully!")
            else:
                self.log_message("Test stopped")
                
        except Exception as e:
            self.log_message(f"Test loop error: {str(e)}")
            self.test_running = False
            
        finally:
            # Ensure load is off
            try:
                if self.instrument:
                    self.safe_write(":SOUR:INP OFF")
                    time.sleep(0.2)
            except:
                pass
                
    def monitor_loop(self):
        """Monitor readings and update GUI"""
        while True:
            try:
                if self.is_connected and self.instrument:
                    # Read measurements with safe timing - these may be cached values
                    voltage, current = self.safe_measure()
                    
                    # Always update GUI with whatever values we have
                    self.current_voltage = voltage
                    self.current_current = current
                    
                    # Update GUI
                    dpg.set_value("voltage_display", f"{voltage:.3f} V")
                    dpg.set_value("current_display", f"{current:.3f} A")
                    dpg.set_value("target_current_display", f"{self.target_current:.3f} A")
                    
                    # Update safety status - but indicate if measurements are stale
                    measurement_age = None
                    if self.last_measurement_success_time:
                        measurement_age = (datetime.now() - self.last_measurement_success_time).total_seconds()
                    
                    if measurement_age is not None and measurement_age > self.measurement_timeout_threshold:
                        # Measurements are stale
                        dpg.set_value("voltage_status", f"Voltage OK (stale data: {measurement_age:.0f}s)")
                        dpg.configure_item("voltage_status", color=(200, 200, 100))
                    else:
                        # Fresh measurements
                        if voltage <= self.voltage_cutoff:
                            if self.voltage_below_cutoff_time is not None:
                                time_below = (datetime.now() - self.voltage_below_cutoff_time).total_seconds()
                                remaining = max(0, self.voltage_cutoff_buffer - time_below)
                                dpg.set_value("voltage_status", f"VOLTAGE LOW! ({remaining:.1f}s)")
                                dpg.configure_item("voltage_status", color=(255, 100, 100))
                            else:
                                dpg.set_value("voltage_status", "VOLTAGE LOW! (Starting buffer)")
                                dpg.configure_item("voltage_status", color=(255, 150, 100))
                        else:
                            dpg.set_value("voltage_status", "Voltage OK")
                            dpg.configure_item("voltage_status", color=(100, 255, 100))
                        
                    # Update load status
                    if current > 0.01:
                        dpg.set_value("load_status", "Load ON")
                        dpg.configure_item("load_status", color=(255, 150, 100))
                    else:
                        dpg.set_value("load_status", "Load OFF")
                        dpg.configure_item("load_status", color=(100, 255, 100))
                        
                # Update test progress
                if self.test_running and self.test_data is not None:
                    total_rows = len(self.test_data)
                    dpg.set_value("progress_bar", self.test_progress)
                    dpg.set_value("row_progress", f"{self.current_row} / {total_rows}")
                    
                    if self.start_time:
                        elapsed = datetime.now() - self.start_time
                        elapsed_str = str(elapsed).split('.')[0]  # Remove microseconds
                        dpg.set_value("time_progress", elapsed_str)
                
                # Update live plot
                if len(self.plot_time) > 1:
                    try:
                        # Convert deques to lists for plotting
                        time_data = list(self.plot_time)
                        voltage_data = list(self.plot_voltage)
                        current_data = list(self.plot_current)
                        
                        # Update plot series
                        dpg.set_value("voltage_series", [time_data, voltage_data])
                        dpg.set_value("current_series", [time_data, current_data])
                        
                        # Auto-fit axes
                        dpg.fit_axis_data("x_axis")
                        dpg.fit_axis_data("y_axis_voltage")
                        dpg.fit_axis_data("y_axis_current")
                        
                    except Exception as e:
                        pass  # Ignore plot update errors
                        
                time.sleep(0.1)  # Update at 10Hz
                
            except Exception as e:
                time.sleep(1)  # Wait longer on error
                
    def run(self):
        """Run the application"""
        self.setup_gui()
        
        try:
            dpg.show_viewport()
            dpg.start_dearpygui()
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Cleanup on exit"""
        try:
            self.stop_test()
            self.disconnect()
        except:
            pass
            
        dpg.destroy_context()

def main():
    """Main function"""
    app = EnduranceTestController()
    app.run()

if __name__ == "__main__":
    main()
