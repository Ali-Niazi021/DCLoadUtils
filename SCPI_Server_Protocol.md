# Rigol DL3021 SCPI Server Communication Protocol

## Overview
This document describes the communication protocol for the Rigol DL3021 SCPI Server running on Raspberry Pi. The server acts as a bridge between network clients and the USB-connected Rigol DL3021 DC Electronic Load.

## Connection Details
- **Protocol**: TCP/IP
- **Default Port**: 5025 (standard SCPI port)
- **IP Address**: Raspberry Pi IP address
- **Encoding**: UTF-8
- **Message Termination**: Each message must end with `\n` (newline)

## Request Format

### SCPI Commands
Send standard SCPI commands directly to the server. The server will forward them to the instrument and return the response.

```
<SCPI_COMMAND>\n
```

**Examples:**
```
*IDN?\n
:MEAS:VOLT?\n
:CURR 1.5\n
:INP ON\n
```

### Special Server Commands
The server also supports special commands for server management:

- `STATUS\n` - Get server and instrument status
- `QUIT\n` or `EXIT\n` - Disconnect from server

## Response Format

All responses from the server are JSON objects with the following structure:

```json
{
    "success": boolean,
    "command": "original_command",
    "response": "instrument_response_or_success_message",
    "error": "error_message_if_any",
    "timestamp": "ISO_timestamp"
}
```

### Successful Response Example
```json
{
    "success": true,
    "command": "*IDN?",
    "response": "RIGOL TECHNOLOGIES,DL3021,DL3A231800370,00.01.05.00.01",
    "error": null,
    "timestamp": "2025-09-14T10:30:45.123456"
}
```

### Error Response Example
```json
{
    "success": false,
    "command": ":INVALID:COMMAND?",
    "response": null,
    "error": "VI_ERROR_TMO (-1073807339): Timeout expired before operation completed.",
    "timestamp": "2025-09-14T10:31:12.654321"
}
```

### Server Status Response
```json
{
    "success": true,
    "response": {
        "server_running": true,
        "instrument_connected": true,
        "instrument_address": "USB0::6833::3601::DL3A231800370::0::INSTR",
        "active_connections": 2
    },
    "timestamp": "2025-09-14T10:32:00.000000"
}
```

## Common SCPI Commands for Rigol DL3021

### Identification and Status
- `*IDN?` - Get instrument identification
- `:SYST:VERS?` - Get system version
- `:SYST:ERR?` - Get system error
- `*RST` - Reset instrument to default settings

### Function Control
- `:FUNC?` - Query current function mode
- `:FUNC CC` - Set to Constant Current mode
- `:FUNC CV` - Set to Constant Voltage mode
- `:FUNC CR` - Set to Constant Resistance mode
- `:FUNC CP` - Set to Constant Power mode

### Current Settings
- `:CURR?` - Query current setting
- `:CURR <value>` - Set current level (e.g., `:CURR 1.5`)
- `:CURR:RANG?` - Query current range
- `:CURR:LEV?` - Query current level

### Voltage Settings
- `:VOLT?` - Query voltage setting
- `:VOLT <value>` - Set voltage level
- `:VOLT:RANG?` - Query voltage range

### Input Control
- `:INP?` - Query input state (0=OFF, 1=ON)
- `:INP ON` - Turn input ON
- `:INP OFF` - Turn input OFF

### Measurements
- `:MEAS:VOLT?` - Measure actual voltage
- `:MEAS:CURR?` - Measure actual current
- `:MEAS:POW?` - Measure actual power

### Protection Settings
- `:VOLT:LIM?` - Query voltage limit
- `:VOLT:LIM <value>` - Set voltage limit
- `:CURR:LIM?` - Query current limit
- `:CURR:LIM <value>` - Set current limit

## Example Client Implementation (Python)

```python
import socket
import json

class RigolClient:
    def __init__(self, host, port=5025):
        self.host = host
        self.port = port
        self.socket = None
    
    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
    
    def send_command(self, command):
        # Send command
        self.socket.send((command + '\n').encode('utf-8'))
        
        # Receive response
        response = self.socket.recv(4096).decode('utf-8').strip()
        return json.loads(response)
    
    def disconnect(self):
        if self.socket:
            self.send_command('QUIT')
            self.socket.close()

# Usage example
client = RigolClient('192.168.1.100')
client.connect()

# Get instrument ID
response = client.send_command('*IDN?')
print(f"Instrument: {response['response']}")

# Set current to 1A
response = client.send_command(':CURR 1.0')
print(f"Set current: {response['success']}")

# Turn input ON
response = client.send_command(':INP ON')
print(f"Input ON: {response['success']}")

# Measure voltage
response = client.send_command(':MEAS:VOLT?')
print(f"Voltage: {response['response']} V")

client.disconnect()
```

## Error Handling

### Connection Errors
- **No response**: Server may be down or unreachable
- **Connection refused**: Check if server is running on correct port
- **Timeout**: Network issues or server overloaded

### Command Errors
- **Invalid SCPI command**: Check command syntax against manual
- **Instrument timeout**: Instrument may be busy or disconnected
- **Permission denied**: Some commands may require specific instrument state

### Best Practices
1. Always check the `success` field in responses
2. Handle network timeouts gracefully
3. Log errors for debugging
4. Implement retry logic for critical commands
5. Close connections properly when done

## Security Considerations
- The server currently has no authentication
- Use on trusted networks only
- Consider implementing IP whitelisting
- Monitor server logs for suspicious activity

## Server Configuration
The server can be configured by modifying these parameters in the script:
- `HOST`: IP address to bind to ('0.0.0.0' for all interfaces)
- `PORT`: TCP port number (default 5025)
- Instrument timeout (default 5 seconds)
- Log file location

## Troubleshooting

### Server Won't Start
1. Check if port 5025 is already in use: `sudo netstat -tlnp | grep 5025`
2. Verify instrument is connected and powered on
3. Check server logs: `tail -f /tmp/rigol_scpi_server.log`

### Commands Fail
1. Test commands directly on instrument first
2. Check SCPI command syntax in Rigol manual
3. Verify instrument is in remote mode
4. Check for instrument errors: Send `:SYST:ERR?`

### Network Issues
1. Verify Raspberry Pi IP address
2. Check firewall settings
3. Test with telnet: `telnet <pi_ip> 5025`
4. Monitor network traffic with tcpdump if needed
