# DC Load Controller GUI

A custom Python GUI application for controlling RIGOL DL3000 series programmable DC loads connected via USB using VISA communication.

## Detected Device
- **Model**: RIGOL DL3021  
- **VISA Address**: USB0::0x1AB1::0x0E11::DL3A231800370::INSTR
- **Specifications**: 41A max, 155V max, 200W max
- **Firmware**: 00.01.05.00.01

## Features

- **Real-time Monitoring**: Display current voltage, current, and power readings
- **Control Interface**: Set current limit, voltage cutoff, and time cutoff parameters
- **Data Visualization**: Real-time plotting of voltage and current over time
- **Safety Features**: Emergency stop button and load enable/disable control
- **Communication Log**: Track all commands sent to and received from the device
- **Data Export**: Save monitoring data to CSV files for analysis
- **VISA Communication**: Uses industry-standard VISA protocol for reliable communication

## Installation

1. Make sure Python 3.7+ is installed on your system
2. Install required packages (already done in this environment):
   ```
   pip install pyvisa pyvisa-py matplotlib numpy
   ```

## Usage

### Quick Start

✅ **Your device is already detected and working!**

1. **Run the main application**:
   ```bash
   python dc_load_controller.py
   ```

2. **Connect**: The VISA address is pre-configured. Just click "Connect"

3. **Start Testing**: Begin with low current limits for safety

### GUI Tabs

#### Control Tab
- **Connection**: Select COM port and connect to device
- **Current Readings**: Real-time display of voltage, current, and power
- **Control Settings**: Set current limit, voltage cutoff, and time cutoff
- **Load Control**: Enable/disable load and emergency stop
- **Quick Commands**: Get status, reset, and clear errors

#### Monitor Tab
- **Real-time Plots**: Voltage and current vs. time graphs
- **Data Control**: Start/stop monitoring, clear data, save to CSV

#### Settings Tab
- **Communication Settings**: Configure baud rate, data bits, etc.
- **Custom Commands**: Send manual SCPI commands and see responses

#### Communication Log Tab
- **Message Log**: All communication with the device
- **Log Control**: Clear and save log files

## Important Setup Notes

Since I couldn't read your PDF manual directly, you'll need to verify and update these items:

### 1. Serial Communication Settings
Check your manual for the correct:
- Baud rate (default: 9600)
- Data bits (default: 8)
- Stop bits (default: 1)
- Parity (default: None)

### 2. SCPI Commands
The application uses common SCPI command patterns. Verify these in your manual:

```python
# Current commands used - update if different:
"MEAS:VOLT?"     # Read voltage
"MEAS:CURR?"     # Read current  
"MEAS:POW?"      # Read power
"CURR 1.000"     # Set current limit
"VOLT:PROT:LOW 2.5"  # Set voltage cutoff
"LOAD ON"        # Enable load
"LOAD OFF"       # Disable load
"*IDN?"          # Device identification
"*RST"           # Reset device
"*CLS"           # Clear errors
```

### 3. Command Termination
Some devices require specific termination characters:
- Line Feed (\\n) - currently used
- Carriage Return + Line Feed (\\r\\n)
- Carriage Return only (\\r)

## Customization

### Adding New Commands
To add custom commands, modify the `send_command()` method or use the Custom Commands tab.

### Changing Update Rates
Modify these variables in the code:
- `update_display()` - GUI update rate
- `communication_worker()` - Monitoring data collection rate

### Safety Features
The application includes:
- Emergency stop button
- Automatic load disable on disconnect
- Error logging
- Parameter validation (you can add limits in the code)

## Troubleshooting

### Connection Issues
1. Check that the correct COM port is selected
2. Verify serial settings match your device
3. Make sure no other software is using the COM port
4. Check USB cable and connections

### Command Errors
1. Use the Communication Log to see exact commands sent
2. Try commands manually in the Settings tab
3. Check command syntax in your device manual
4. Verify command termination characters

### No Response from Device
1. Check if device is in remote control mode
2. Try sending "*IDN?" command manually
3. Verify baud rate and communication settings
4. Check device manual for any initialization requirements

## Files Created

- `dc_load_controller.py` - Main GUI application
- `config.ini` - Configuration file for settings
- `README.md` - This documentation file

## Safety Warning

⚠️ **Always use the emergency stop button if anything goes wrong during testing. This application is designed to control potentially dangerous high-power equipment. Always verify your setup and test with safe parameters first.**

## Next Steps

1. **Read your DL3000 manual** and update the SCPI commands as needed
2. **Test communication** using the Settings tab before running tests
3. **Start with low current limits** to verify safe operation
4. **Verify voltage cutoff** settings work properly
5. **Test emergency stop** functionality before connecting batteries

## Data Analysis

The application saves data in CSV format with columns:
- Time (seconds)
- Voltage (V)
- Current (A) 
- Power (W)

You can import this data into Excel, Python pandas, or other analysis tools for further processing.
