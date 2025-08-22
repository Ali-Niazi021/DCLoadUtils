#!/usr/bin/env python3
"""
DC Load Controller GUI
A custom GUI for controlling a programmable DC Load through USB/Serial communication.
Designed for DL3000 series DC loads.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pyvisa
import threading
import time
import queue
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

class DCLoadController:
    def __init__(self, root):
        self.root = root
        self.root.title("DC Load Controller - DL3000 Series")
        self.root.geometry("1200x800")
        
        # VISA connection
        self.rm = pyvisa.ResourceManager()
        self.visa_conn = None
        self.is_connected = False
        self.monitoring_active = False
        
        # Default VISA address
        self.visa_address = "USB0::0x1AB1::0x0E11::DL3A231800370::INSTR"
        
        # Data storage for plotting
        self.time_data = []
        self.voltage_data = []
        self.current_data = []
        self.power_data = []
        self.max_data_points = 1000
        
        # Communication queue
        self.comm_queue = queue.Queue()
        
        # Current readings
        self.current_voltage = tk.StringVar(value="0.000")
        self.current_current = tk.StringVar(value="0.000")
        self.current_power = tk.StringVar(value="0.000")
        
        # Control settings
        self.current_limit = tk.StringVar(value="1.000")
        self.voltage_cutoff = tk.StringVar(value="2.500")
        self.time_cutoff = tk.StringVar(value="3600")
        self.load_enabled = tk.BooleanVar()
        
        # Battery mode settings
        self.battery_mode_enabled = tk.BooleanVar(value=True)
        self.current_range = tk.StringVar(value="LOW")
        self.function_mode = tk.StringVar(value="CC")
        
        # Device status
        self.device_function_mode = tk.StringVar(value="Unknown")
        self.device_control_mode = tk.StringVar(value="Unknown")
        
        # Setup GUI
        self.setup_gui()
        
        # Start communication thread
        self.comm_thread = threading.Thread(target=self.communication_worker, daemon=True)
        self.comm_thread.start()
        
        # Start data update loop
        self.update_display()
        
    def setup_gui(self):
        # Create main notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Control Tab
        control_frame = ttk.Frame(notebook)
        notebook.add(control_frame, text="Control")
        self.setup_control_tab(control_frame)
        
        # Monitor Tab
        monitor_frame = ttk.Frame(notebook)
        notebook.add(monitor_frame, text="Monitor")
        self.setup_monitor_tab(monitor_frame)
        
        # Settings Tab
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="Settings")
        self.setup_settings_tab(settings_frame)
        
        # Log Tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Communication Log")
        self.setup_log_tab(log_frame)
        
    def setup_control_tab(self, parent):
        # Connection Frame
        conn_frame = ttk.LabelFrame(parent, text="Connection", padding=10)
        conn_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(conn_frame, text="VISA Address:").grid(row=0, column=0, sticky='w')
        self.visa_address_var = tk.StringVar(value=self.visa_address)
        visa_entry = ttk.Entry(conn_frame, textvariable=self.visa_address_var, width=50)
        visa_entry.grid(row=0, column=1, padx=5, columnspan=2)
        
        ttk.Button(conn_frame, text="Refresh Resources", command=self.refresh_visa_resources).grid(row=0, column=3, padx=5)
        
        # Available resources list
        ttk.Label(conn_frame, text="Available Resources:").grid(row=1, column=0, sticky='w')
        self.resource_combo = ttk.Combobox(conn_frame, width=50, state="readonly")
        self.resource_combo.grid(row=1, column=1, padx=5, columnspan=2)
        self.resource_combo.bind('<<ComboboxSelected>>', self.on_resource_selected)
        
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=2, column=0, padx=5, pady=10)
        
        self.status_label = ttk.Label(conn_frame, text="Disconnected", foreground="red")
        self.status_label.grid(row=2, column=1, padx=10, sticky='w')
        
        # Current Readings Frame
        readings_frame = ttk.LabelFrame(parent, text="Current Readings", padding=10)
        readings_frame.pack(fill='x', padx=10, pady=5)
        
        # Create a grid for readings
        ttk.Label(readings_frame, text="Voltage:", font=('Arial', 12, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(readings_frame, textvariable=self.current_voltage, font=('Arial', 12), 
                 foreground='blue').grid(row=0, column=1, sticky='w')
        ttk.Label(readings_frame, text="V", font=('Arial', 12)).grid(row=0, column=2, sticky='w')
        
        ttk.Label(readings_frame, text="Current:", font=('Arial', 12, 'bold')).grid(row=1, column=0, sticky='w')
        ttk.Label(readings_frame, textvariable=self.current_current, font=('Arial', 12), 
                 foreground='orange').grid(row=1, column=1, sticky='w')
        ttk.Label(readings_frame, text="A", font=('Arial', 12)).grid(row=1, column=2, sticky='w')
        
        ttk.Label(readings_frame, text="Power:", font=('Arial', 12, 'bold')).grid(row=2, column=0, sticky='w')
        ttk.Label(readings_frame, textvariable=self.current_power, font=('Arial', 12), 
                 foreground='red').grid(row=2, column=1, sticky='w')
        ttk.Label(readings_frame, text="W", font=('Arial', 12)).grid(row=2, column=2, sticky='w')
        
        # Control Settings Frame
        control_frame = ttk.LabelFrame(parent, text="Control Settings", padding=10)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        # Battery Mode Settings
        battery_frame = ttk.LabelFrame(control_frame, text="Battery Mode", padding=5)
        battery_frame.grid(row=0, column=0, columnspan=3, sticky='ew', padx=5, pady=5)
        
        battery_check = ttk.Checkbutton(battery_frame, text="Enable Battery Mode", 
                                       variable=self.battery_mode_enabled,
                                       command=self.toggle_battery_mode)
        battery_check.grid(row=0, column=0, sticky='w', padx=5)
        
        ttk.Label(battery_frame, text="Function:").grid(row=0, column=1, padx=5)
        func_combo = ttk.Combobox(battery_frame, textvariable=self.function_mode, 
                                 values=["CC", "CV", "CP", "CR"], width=8, state="readonly")
        func_combo.grid(row=0, column=2, padx=5)
        func_combo.bind('<<ComboboxSelected>>', self.on_function_change)
        
        ttk.Label(battery_frame, text="Range:").grid(row=0, column=3, padx=5)
        range_combo = ttk.Combobox(battery_frame, textvariable=self.current_range,
                                  values=["LOW", "HIGH"], width=8, state="readonly")
        range_combo.grid(row=0, column=4, padx=5)
        range_combo.bind('<<ComboboxSelected>>', self.on_range_change)
        
        # Current Limit
        ttk.Label(control_frame, text="Current Limit (A):").grid(row=1, column=0, sticky='w', pady=2)
        current_entry = ttk.Entry(control_frame, textvariable=self.current_limit, width=10)
        current_entry.grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(control_frame, text="Set", 
                  command=self.set_current_limit).grid(row=1, column=2, padx=5)
        
        # Voltage Cutoff
        ttk.Label(control_frame, text="Voltage Cutoff (V):").grid(row=2, column=0, sticky='w', pady=2)
        voltage_entry = ttk.Entry(control_frame, textvariable=self.voltage_cutoff, width=10)
        voltage_entry.grid(row=2, column=1, padx=5, pady=2)
        ttk.Button(control_frame, text="Set", 
                  command=self.set_voltage_cutoff).grid(row=2, column=2, padx=5)
        
        # Time Cutoff (for future implementation)
        ttk.Label(control_frame, text="Time Cutoff (s):").grid(row=3, column=0, sticky='w', pady=2)
        time_entry = ttk.Entry(control_frame, textvariable=self.time_cutoff, width=10)
        time_entry.grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(control_frame, text="Set", 
                  command=self.set_time_cutoff).grid(row=3, column=2, padx=5)
        
        # Device Status Display
        status_frame = ttk.LabelFrame(parent, text="Device Status", padding=10)
        status_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(status_frame, text="Function Mode:").grid(row=0, column=0, sticky='w')
        ttk.Label(status_frame, textvariable=self.device_function_mode, foreground='blue').grid(row=0, column=1, sticky='w', padx=10)
        
        ttk.Label(status_frame, text="Control Mode:").grid(row=0, column=2, sticky='w', padx=10)
        ttk.Label(status_frame, textvariable=self.device_control_mode, foreground='blue').grid(row=0, column=3, sticky='w', padx=10)
        
        # Load Control
        load_frame = ttk.LabelFrame(parent, text="Load Control", padding=10)
        load_frame.pack(fill='x', padx=10, pady=5)
        
        self.load_toggle = ttk.Checkbutton(load_frame, text="Load Enabled", 
                                          variable=self.load_enabled, 
                                          command=self.toggle_load)
        self.load_toggle.pack(side='left', padx=10)
        
        ttk.Button(load_frame, text="Emergency Stop", command=self.emergency_stop,
                  style='Emergency.TButton').pack(side='right', padx=10)
        
        # Configure emergency button style
        style = ttk.Style()
        style.configure('Emergency.TButton', foreground='white')
        
        # Quick Commands
        quick_frame = ttk.LabelFrame(parent, text="Quick Commands", padding=10)
        quick_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(quick_frame, text="Setup Battery Mode", command=self.setup_battery_mode).pack(side='left', padx=5)
        ttk.Button(quick_frame, text="Get Status", command=self.get_status).pack(side='left', padx=5)
        ttk.Button(quick_frame, text="Reset Device", command=self.reset_device).pack(side='left', padx=5)
        ttk.Button(quick_frame, text="Clear Errors", command=self.clear_errors).pack(side='left', padx=5)        # Initialize VISA resources
        self.refresh_visa_resources()
        
    def setup_monitor_tab(self, parent):
        # Create matplotlib figure
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))
        self.fig.tight_layout(pad=3.0)
        
        # Voltage plot
        self.ax1.set_title('Voltage vs Time')
        self.ax1.set_ylabel('Voltage (V)')
        self.ax1.grid(True)
        
        # Current plot
        self.ax2.set_title('Current vs Time')
        self.ax2.set_xlabel('Time (s)')
        self.ax2.set_ylabel('Current (A)')
        self.ax2.grid(True)
        
        # Embed plot in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, parent)
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
        
        # Control buttons for monitoring
        monitor_control = ttk.Frame(parent)
        monitor_control.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(monitor_control, text="Start Monitoring", 
                  command=self.start_monitoring).pack(side='left', padx=5)
        ttk.Button(monitor_control, text="Stop Monitoring", 
                  command=self.stop_monitoring).pack(side='left', padx=5)
        ttk.Button(monitor_control, text="Clear Data", 
                  command=self.clear_data).pack(side='left', padx=5)
        ttk.Button(monitor_control, text="Save Data", 
                  command=self.save_data).pack(side='left', padx=5)
        
    def setup_settings_tab(self, parent):
        # VISA Settings
        visa_frame = ttk.LabelFrame(parent, text="VISA Settings", padding=10)
        visa_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(visa_frame, text="Timeout (ms):").grid(row=0, column=0, sticky='w')
        self.timeout_var = tk.StringVar(value="5000")
        timeout_entry = ttk.Entry(visa_frame, textvariable=self.timeout_var)
        timeout_entry.grid(row=0, column=1, padx=5)
        
        ttk.Button(visa_frame, text="Apply Timeout", 
                  command=self.apply_timeout).grid(row=0, column=2, padx=5)
        
        # Device Information
        info_frame = ttk.LabelFrame(parent, text="Device Information", padding=10)
        info_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(info_frame, text="Get Device Info", 
                  command=self.get_device_info).pack(side='left', padx=5)
        
        self.device_info_text = scrolledtext.ScrolledText(info_frame, height=4, width=60)
        self.device_info_text.pack(fill='x', pady=(10,0))
        
        # Custom Command Frame
        cmd_frame = ttk.LabelFrame(parent, text="Custom Commands", padding=10)
        cmd_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        ttk.Label(cmd_frame, text="Command:").pack(anchor='w')
        self.custom_cmd = tk.StringVar()
        cmd_entry = ttk.Entry(cmd_frame, textvariable=self.custom_cmd, width=50)
        cmd_entry.pack(fill='x', pady=2)
        cmd_entry.bind('<Return>', lambda e: self.send_custom_command())
        
        ttk.Button(cmd_frame, text="Send", command=self.send_custom_command).pack(pady=5)
        
        ttk.Label(cmd_frame, text="Response:").pack(anchor='w', pady=(10,0))
        self.response_text = scrolledtext.ScrolledText(cmd_frame, height=10, width=60)
        self.response_text.pack(fill='both', expand=True, pady=2)
        
    def setup_log_tab(self, parent):
        # Communication log
        self.log_text = scrolledtext.ScrolledText(parent, height=30, width=80)
        self.log_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Log controls
        log_controls = ttk.Frame(parent)
        log_controls.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(log_controls, text="Clear Log", command=self.clear_log).pack(side='left', padx=5)
        ttk.Button(log_controls, text="Save Log", command=self.save_log).pack(side='left', padx=5)
        
    def refresh_visa_resources(self):
        """Refresh the list of available VISA resources"""
        try:
            resources = self.rm.list_resources()
            self.resource_combo['values'] = list(resources)
            
            # If our specific DC Load is found, select it
            if self.visa_address in resources:
                self.resource_combo.set(self.visa_address)
                self.visa_address_var.set(self.visa_address)
            elif resources:
                self.resource_combo.set(resources[0])
                
            self.log_message(f"Found {len(resources)} VISA resources")
            for resource in resources:
                self.log_message(f"  - {resource}")
                
        except Exception as e:
            self.log_message(f"Error refreshing VISA resources: {str(e)}")
            
    def on_resource_selected(self, event):
        """Update VISA address when resource is selected from dropdown"""
        selected = self.resource_combo.get()
        if selected:
            self.visa_address_var.set(selected)
            self.visa_address = selected
            
    def toggle_connection(self):
        """Connect or disconnect from the DC load"""
        if not self.is_connected:
            self.connect()
        else:
            self.disconnect()
            
    def connect(self):
        """Establish connection to DC load via VISA"""
        try:
            visa_addr = self.visa_address_var.get().strip()
            if not visa_addr:
                messagebox.showerror("Error", "Please enter a VISA address")
                return
                
            self.log_message(f"Attempting to connect to {visa_addr}")
            
            # Open VISA connection
            self.visa_conn = self.rm.open_resource(visa_addr)
            
            # Configure timeout
            self.visa_conn.timeout = 5000  # 5 second timeout
            
            # Test connection with identification query
            idn_response = self.visa_conn.query("*IDN?")
            self.log_message(f"Device identification: {idn_response.strip()}")
            
            self.is_connected = True
            self.visa_address = visa_addr
            self.connect_btn.config(text="Disconnect")
            self.status_label.config(text="Connected", foreground="green")
            self.log_message("Successfully connected to DC Load")
            
            # Safety first - ensure load is off
            self.visa_conn.write(":SOUR:INP OFF")
            self.load_enabled.set(False)
            
            # Initialize battery mode if enabled
            if self.battery_mode_enabled.get():
                self.setup_battery_mode()
            else:
                # Get initial status
                self.get_status()
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {str(e)}")
            self.log_message(f"Connection failed: {str(e)}")
            if self.visa_conn:
                try:
                    self.visa_conn.close()
                except:
                    pass
                self.visa_conn = None
            
    def disconnect(self):
        """Disconnect from DC load"""
        try:
            if self.visa_conn:
                # Turn off load before disconnecting
                try:
                    self.visa_conn.write(":SOUR:INP OFF")
                    self.load_enabled.set(False)
                except:
                    pass  # Ignore errors during shutdown
                self.visa_conn.close()
                
            self.is_connected = False
            self.monitoring_active = False
            self.visa_conn = None
            self.connect_btn.config(text="Connect")
            self.status_label.config(text="Disconnected", foreground="red")
            self.log_message("Disconnected from DC Load")
            
        except Exception as e:
            self.log_message(f"Disconnect error: {str(e)}")
            self.visa_conn = None
            
    def send_command(self, command, expect_response=False):
        """Send command to DC load via VISA"""
        if not self.is_connected or not self.visa_conn:
            self.log_message("Not connected to DC Load")
            return None
            
        try:
            self.log_message(f"SENT: {command.strip()}")
            
            if expect_response:
                response = self.visa_conn.query(command).strip()
                self.log_message(f"RECV: {response}")
                return response
            else:
                self.visa_conn.write(command)
                return None
                
        except Exception as e:
            self.log_message(f"Command error: {str(e)}")
            return None
            
    def apply_timeout(self):
        """Apply timeout setting to VISA connection"""
        if self.visa_conn:
            try:
                timeout_ms = int(self.timeout_var.get())
                self.visa_conn.timeout = timeout_ms
                self.log_message(f"Timeout set to {timeout_ms} ms")
            except ValueError:
                messagebox.showerror("Error", "Invalid timeout value")
            except Exception as e:
                self.log_message(f"Error setting timeout: {str(e)}")
                
    def get_device_info(self):
        """Get comprehensive device information"""
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to device first")
            return
            
        info_commands = [
            ("*IDN?", "Identification"),
            ("*OPT?", "Options"),
            ("SYST:ERR?", "System Errors"),
            ("SYST:VERS?", "SCPI Version"),
            ("CURR? MAX", "Max Current"),
            ("VOLT? MAX", "Max Voltage"),
            ("POW? MAX", "Max Power")
        ]
        
        info_text = ""
        for cmd, description in info_commands:
            try:
                response = self.send_command(cmd, expect_response=True)
                if response:
                    info_text += f"{description}: {response}\n"
                else:
                    info_text += f"{description}: No response\n"
            except Exception as e:
                info_text += f"{description}: Error - {str(e)}\n"
                
        self.device_info_text.delete("1.0", tk.END)
        self.device_info_text.insert("1.0", info_text)
        
    def send_custom_command(self):
        """Send custom command and display response"""
        command = self.custom_cmd.get().strip()
        if not command:
            return
            
        response = self.send_command(command, expect_response=True)
        if response:
            self.response_text.insert(tk.END, f"CMD: {command}\nRESP: {response}\n\n")
            self.response_text.see(tk.END)
            
    def get_status(self):
        """Get current status from DC load"""
        if not self.is_connected:
            return
            
        try:
            # Query voltage, current, and power
            voltage = self.send_command(":MEAS:VOLT?", expect_response=True)
            current = self.send_command(":MEAS:CURR?", expect_response=True)
            power = self.send_command(":MEAS:POW?", expect_response=True)
            
            # Query device status
            func_mode = self.send_command(":SOUR:FUNC?", expect_response=True)
            control_mode = self.send_command(":SOUR:FUNC:MODE?", expect_response=True)
            
            # Update readings
            if voltage:
                self.current_voltage.set(f"{float(voltage):.3f}")
            if current:
                self.current_current.set(f"{float(current):.3f}")
            if power:
                self.current_power.set(f"{float(power):.3f}")
                
            # Update device status
            if func_mode:
                self.device_function_mode.set(func_mode)
            if control_mode:
                self.device_control_mode.set(control_mode)
                
        except (ValueError, TypeError) as e:
            self.log_message(f"Status parsing error: {str(e)}")
        except Exception as e:
            self.log_message(f"Status query error: {str(e)}")
            
    def toggle_battery_mode(self):
        """Toggle battery mode on/off"""
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to device first")
            return
            
        try:
            if self.battery_mode_enabled.get():
                # Enable battery mode
                self.send_command(":SOUR:FUNC:MODE BATT")
                self.log_message("Battery mode enabled")
            else:
                # Disable battery mode (use fixed mode)
                self.send_command(":SOUR:FUNC:MODE FIX") 
                self.log_message("Battery mode disabled (fixed mode)")
                
            # Update status
            self.get_status()
            
        except Exception as e:
            self.log_message(f"Battery mode toggle error: {str(e)}")
            
    def on_function_change(self, event=None):
        """Handle function mode change"""
        if not self.is_connected:
            return
            
        try:
            func = self.function_mode.get()
            if func == "CC":
                self.send_command(":SOUR:FUNC CURR")
            elif func == "CV":
                self.send_command(":SOUR:FUNC VOLT")
            elif func == "CP":
                self.send_command(":SOUR:FUNC POW")
            elif func == "CR":
                self.send_command(":SOUR:FUNC RES")
                
            self.log_message(f"Function set to {func}")
            self.get_status()
            
        except Exception as e:
            self.log_message(f"Function change error: {str(e)}")
            
    def on_range_change(self, event=None):
        """Handle current range change"""
        if not self.is_connected:
            return
            
        try:
            range_val = self.current_range.get()
            self.send_command(f":SOUR:CURR:RANG {range_val}")
            self.log_message(f"Current range set to {range_val}")
            self.get_status()
            
        except Exception as e:
            self.log_message(f"Range change error: {str(e)}")
            
    def set_current_limit(self):
        """Set current limit"""
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to device first")
            return
            
        try:
            current = float(self.current_limit.get())
            self.send_command(f":SOUR:CURR:LEV {current}")
            self.log_message(f"Current limit set to {current}A")
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid current value")
        except Exception as e:
            self.log_message(f"Current limit error: {str(e)}")
            
    def set_voltage_cutoff(self):
        """Set voltage cutoff"""
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to device first")
            return
            
        try:
            voltage = float(self.voltage_cutoff.get())
            self.send_command(f":VOLT:PROT:LOW {voltage}")
            self.log_message(f"Voltage cutoff set to {voltage}V")
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid voltage value")
        except Exception as e:
            self.log_message(f"Voltage cutoff error: {str(e)}")
            
    def set_time_cutoff(self):
        """Set time cutoff (placeholder for future implementation)"""
        self.log_message("Time cutoff setting not yet implemented")
        
    def setup_battery_mode(self):
        """Setup complete battery mode configuration"""
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to device first")
            return
            
        try:
            self.log_message("Setting up battery mode...")
            
            # Safety first - turn off load
            self.send_command(":SOUR:INP OFF")
            self.load_enabled.set(False)
            
            # Clear errors
            self.send_command("*CLS")
            
            # Set function mode
            func = self.function_mode.get()
            if func == "CC":
                self.send_command(":SOUR:FUNC CURR")
            elif func == "CV": 
                self.send_command(":SOUR:FUNC VOLT")
            elif func == "CP":
                self.send_command(":SOUR:FUNC POW") 
            elif func == "CR":
                self.send_command(":SOUR:FUNC RES")
                
            # Enable battery mode if selected
            if self.battery_mode_enabled.get():
                self.send_command(":SOUR:FUNC:MODE BATT")
            else:
                self.send_command(":SOUR:FUNC:MODE FIX")
                
            # Set current range
            range_val = self.current_range.get()
            self.send_command(f":SOUR:CURR:RANG {range_val}")
            
            # Set current limit
            current = float(self.current_limit.get())
            self.send_command(f":SOUR:CURR:LEV {current}")
            
            # Set voltage cutoff
            voltage = float(self.voltage_cutoff.get())
            self.send_command(f":VOLT:PROT:LOW {voltage}")
            
            self.log_message("Battery mode setup completed")
            self.get_status()
            
            messagebox.showinfo("Setup Complete", "Battery mode has been configured successfully!")
            
        except Exception as e:
            self.log_message(f"Battery mode setup error: {str(e)}")
            messagebox.showerror("Setup Error", f"Failed to setup battery mode: {str(e)}")
            
    def reset_device(self):
        """Reset the device"""
        if not self.is_connected:
            return
            
        try:
            self.send_command("*RST")
            self.log_message("Device reset")
            time.sleep(1)  # Give device time to reset
            self.get_status()
            
        except Exception as e:
            self.log_message(f"Reset error: {str(e)}")
            
    def clear_errors(self):
        """Clear device errors"""
        if not self.is_connected:
            return
            
        try:
            self.send_command("*CLS")
            self.log_message("Errors cleared")
            
        except Exception as e:
            self.log_message(f"Clear errors failed: {str(e)}")
            
    def toggle_load(self):
        """Toggle load on/off"""
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to device first")
            return
            
        try:
            if self.load_enabled.get():
                self.send_command(":SOUR:INP ON")
                self.log_message("Load enabled")
            else:
                self.send_command(":SOUR:INP OFF")
                self.log_message("Load disabled")
                
        except Exception as e:
            self.log_message(f"Load toggle error: {str(e)}")
            # Reset checkbox state on error
            self.load_enabled.set(not self.load_enabled.get())
            
    def emergency_stop(self):
        """Emergency stop - immediately turn off load"""
        try:
            if self.visa_conn:
                self.visa_conn.write(":SOUR:INP OFF")
                
            self.load_enabled.set(False)
            self.log_message("EMERGENCY STOP ACTIVATED")
            messagebox.showwarning("Emergency Stop", "Load has been turned off!")
            
        except Exception as e:
            self.log_message(f"Emergency stop error: {str(e)}")
            messagebox.showerror("Emergency Stop Error", 
                               "Failed to turn off load! Check connection and manually disable load!")
        
    def start_monitoring(self):
        """Start continuous monitoring"""
        self.monitoring_active = True
        self.log_message("Monitoring started")
        
    def stop_monitoring(self):
        """Stop continuous monitoring"""
        self.monitoring_active = False
        self.log_message("Monitoring stopped")
        
    def clear_data(self):
        """Clear monitoring data"""
        self.time_data.clear()
        self.voltage_data.clear()
        self.current_data.clear()
        self.power_data.clear()
        self.update_plot()
        self.log_message("Data cleared")
        
    def save_data(self):
        """Save monitoring data to CSV file"""
        if not self.time_data:
            messagebox.showwarning("No Data", "No data to save")
            return
            
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dc_load_data_{timestamp}.csv"
            
            with open(filename, 'w') as f:
                f.write("Time(s),Voltage(V),Current(A),Power(W)\n")
                for i in range(len(self.time_data)):
                    f.write(f"{self.time_data[i]:.2f},{self.voltage_data[i]:.3f},"
                           f"{self.current_data[i]:.3f},{self.power_data[i]:.3f}\n")
                           
            messagebox.showinfo("Data Saved", f"Data saved to {filename}")
            self.log_message(f"Data saved to {filename}")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save data: {str(e)}")
            
    def update_plot(self):
        """Update the monitoring plots"""
        if not self.time_data:
            return
            
        self.ax1.clear()
        self.ax2.clear()
        
        # Voltage plot
        self.ax1.plot(self.time_data, self.voltage_data, 'b-', linewidth=2)
        self.ax1.set_title('Voltage vs Time')
        self.ax1.set_ylabel('Voltage (V)')
        self.ax1.grid(True)
        
        # Current plot
        self.ax2.plot(self.time_data, self.current_data, 'r-', linewidth=2)
        self.ax2.set_title('Current vs Time')
        self.ax2.set_xlabel('Time (s)')
        self.ax2.set_ylabel('Current (A)')
        self.ax2.grid(True)
        
        self.canvas.draw()
        
    def communication_worker(self):
        """Background thread for continuous communication"""
        start_time = time.time()
        
        while True:
            if self.is_connected and self.monitoring_active:
                try:
                    # Get readings
                    voltage = self.send_command(":MEAS:VOLT?", expect_response=True)
                    current = self.send_command(":MEAS:CURR?", expect_response=True)
                    power = self.send_command(":MEAS:POW?", expect_response=True)
                    
                    if voltage and current and power:
                        current_time = time.time() - start_time
                        
                        # Add to data arrays
                        self.time_data.append(current_time)
                        self.voltage_data.append(float(voltage))
                        self.current_data.append(float(current))
                        self.power_data.append(float(power))
                        
                        # Limit data points
                        if len(self.time_data) > self.max_data_points:
                            self.time_data.pop(0)
                            self.voltage_data.pop(0)
                            self.current_data.pop(0)
                            self.power_data.pop(0)
                            
                except Exception as e:
                    self.log_message(f"Monitoring error: {str(e)}")
                    
            time.sleep(0.5)  # Update every 500ms
            
    def update_display(self):
        """Update the display with current readings"""
        try:
            if self.is_connected and not self.monitoring_active:
                # Get status periodically even when not monitoring
                self.root.after(2000, lambda: self.get_status())
                
            # Update plot if monitoring
            if self.monitoring_active and self.time_data:
                self.update_plot()
                
        except Exception as e:
            self.log_message(f"Display update error: {str(e)}")
            
        # Schedule next update
        self.root.after(1000, lambda: self.update_display())
        
    def log_message(self, message):
        """Add message to communication log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        # Store messages in a buffer if log_text isn't ready yet
        if not hasattr(self, 'log_text'):
            if not hasattr(self, '_log_buffer'):
                self._log_buffer = []
            self._log_buffer.append(log_entry)
            print(log_entry.strip())  # Print to console for now
            return
        
        # Add buffered messages if any
        if hasattr(self, '_log_buffer'):
            for buffered_msg in self._log_buffer:
                self.log_text.insert(tk.END, buffered_msg)
            del self._log_buffer
        
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        
        # Limit log size
        lines = self.log_text.get("1.0", tk.END).split('\n')
        if len(lines) > 1000:
            self.log_text.delete("1.0", f"{len(lines)-1000}.0")
            
    def clear_log(self):
        """Clear the communication log"""
        self.log_text.delete("1.0", tk.END)
        
    def save_log(self):
        """Save communication log to file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dc_load_log_{timestamp}.txt"
            
            with open(filename, 'w') as f:
                f.write(self.log_text.get("1.0", tk.END))
                
            messagebox.showinfo("Log Saved", f"Log saved to {filename}")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save log: {str(e)}")

def main():
    root = tk.Tk()
    app = DCLoadController(root)
    
    # Handle window closing
    def on_closing():
        if app.is_connected:
            app.emergency_stop()
            app.disconnect()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
