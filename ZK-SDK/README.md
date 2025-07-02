# UHF RFID Reader Python SDK

A Python implementation of the UHF RFID Reader SDK, providing functionality for communicating with UHF RFID readers via serial (COM) and network (TCP) connections. This SDK is designed to be a direct port of the C# UHF RFID Reader SDK, maintaining the same method signatures, parameter types, and behavior.

## Features

- **C# SDK Compatibility**: Direct port of the C# UHF RFID Reader SDK with matching method signatures and behavior
- **Serial and TCP Connections**: Support for both serial (COM) and network (TCP) connections
- **Cross-platform**: Works on Windows, macOS, and Linux with automatic port detection
- **Tag Inventory Operations**: Perform Gen2 inventory operations to detect RFID tags
- **Read/Write Operations**: Read and write data to RFID tags
- **Reader Configuration**: Configure reader parameters like RF power, baud rate, address, etc.
- **Real-time Tag Detection**: Continuous inventory with callback support
- **Error Handling**: Comprehensive error handling with custom exceptions
- **Two-tier Architecture**: High-level `UHFReader` class for easy use, low-level `Reader` class for C# compatibility

## Installation

### Prerequisites

- Python 3.7 or higher
- pyserial library

### Install from source

```bash
git clone <repository-url>
cd PythonSDK
pip install -e .
```

### Install dependencies

```bash
pip install pyserial
```

## Architecture

The SDK is designed with a two-tier architecture to provide both ease of use and C# SDK compatibility:

### High-level API (`UHFReader` class)

- **Purpose**: Easy-to-use interface for most applications
- **Parameter Types**: Accepts Python-friendly types (int, str, bytes)
- **Usage**: Recommended for new applications and general use

### Low-level API (`Reader` class)

- **Purpose**: Direct port of the C# SDK with matching signatures
- **Parameter Types**: Uses exact C# parameter types (bytes, bytearray for ref parameters)
- **Usage**: For applications requiring exact C# SDK compatibility

### Parameter Type Conversion

The high-level API automatically converts parameters to the correct types for the low-level API:

```python
# High-level API (user-friendly)
reader.inventory_g2(q_value=4, session=0, scan_time=20)

# Low-level API (C# compatible)
reader.uhf.inventory_g2(
    com_addr=bytearray([255]),
    q_value=bytes([4]),
    session=bytes([0]),
    scan_time=bytes([20]),
    # ... other parameters
)
```

## Quick Start

### Basic Usage

```python
from PythonSDK import UHFReader, RFIDTag

# Create reader instance
reader = UHFReader()

# Connect via serial port
# Windows: Use port number (e.g., 1 for COM1)
# macOS/Linux: Use port number (e.g., 1 for first available port) or device path
result = reader.open_com_port(port=1, com_addr=255, baud=5)  # 57600 baud
if result == 0:
    print("Connected successfully!")

    # Get reader information
    info = reader.get_reader_information()
    print(f"Reader info: {info}")

    # Perform inventory
    tags = reader.inventory_g2(scan_time=5)
    for tag in tags:
        print(f"Found tag: {tag.uid}")

    # Close connection
    reader.close_com_port()
else:
    print(f"Connection failed: {result}")
```

### Cross-platform Port Usage

The SDK supports different port naming conventions across operating systems:

#### Windows

```python
# Use port numbers (COM1, COM2, etc.)
reader.open_com_port(port=1, com_addr=255, baud=5)  # COM1
reader.open_com_port(port=2, com_addr=255, baud=5)  # COM2
```

#### macOS/Linux

```python
# Option 1: Use port index (1 = first available port, 2 = second, etc.)
reader.open_com_port(port=1, com_addr=255, baud=5)  # First available port

# Option 2: Use specific device path
reader.open_com_port(port="/dev/tty.usbserial-10", com_addr=255, baud=5)
reader.open_com_port(port="/dev/ttyUSB0", com_addr=255, baud=5)
reader.open_com_port(port="/dev/ttyACM0", com_addr=255, baud=5)
```

#### Testing with Non-RFID Devices

If you're testing with a device that's not an RFID reader, you can skip the reader verification:

```python
# Skip verification for testing (useful for development/debugging)
reader.open_com_port(port=1, com_addr=255, baud=5, skip_verification=True)
```

**Note:** When using `skip_verification=True`, the SDK will connect to any serial device without verifying it's an RFID reader. RFID operations may fail if the device doesn't support the RFID protocol.

#### Finding Available Ports

```python
# List all available serial ports
available_ports = reader.get_available_ports()
print(f"Available ports: {available_ports}")

# Check if a specific port is available
if reader.is_port_available("/dev/tty.usbserial-10"):
    print("Port is available!")
```

### Network Connection

```python
# Connect via TCP
result = reader.open_net_port(port=8080, ip_addr="192.168.1.100", com_addr=255)
if result == 0:
    print("Network connection established!")
```

### Continuous Inventory with Callback

```python
def tag_callback(tag: RFIDTag):
    print(f"Tag detected: {tag.uid} on antenna {tag.ant}")

# Set callback function
reader.init_rfid_callback(tag_callback)

# Start continuous inventory
reader.start_inventory()

# Let it run for some time
import time
time.sleep(30)

# Stop inventory
reader.stop_inventory()
```

### Read/Write Operations

```python
# Read data from tag
epc = "E200341201B8020110B8A8"
try:
    data = reader.read_data_g2(epc, mem=3, word_ptr=0, num=4)
    print(f"Read data: {data.hex()}")
except Exception as e:
    print(f"Read failed: {e}")

# Write data to tag
write_data = b"Hello RFID!"
try:
    result = reader.write_data_g2(epc, write_data, mem=3, word_ptr=0)
    if result == 0:
        print("Write successful!")
    else:
        print(f"Write failed: {result}")
except Exception as e:
    print(f"Write failed: {e}")
```

## API Reference

### UHFReader Class

#### Connection Methods

- `open_com_port(port, com_addr, baud, skip_verification)` - Open serial connection
  - `port`: int (Windows: COM number, macOS/Linux: port index) or str (device path)
  - `com_addr`: Communication address
  - `baud`: Baud rate code (0=9600, 1=19200, 2=38400, 5=57600, 6=115200)
  - `skip_verification`: Skip reader verification (for testing with non-RFID devices)
- `close_com_port()` - Close serial connection
- `open_net_port(port, ip_addr, com_addr)` - Open network connection
- `close_net_port()` - Close network connection
- `auto_open_com_port(com_addr, baud)` - Auto-detect and open COM port

#### Configuration Methods

- `get_reader_information()` - Get reader information
- `set_region(dmax_fre, dmin_fre)` - Set frequency region
- `set_address(new_addr)` - Set reader address
- `set_inventory_scan_time(scan_time)` - Set inventory scan time
- `set_baud_rate(baud)` - Set baud rate
- `set_rf_power(power_dbm)` - Set RF power

#### Operation Methods

- `inventory_g2(q_value, session, scan_time, target, in_ant)` - Perform Gen2 inventory
- `read_data_g2(epc, mem, word_ptr, num, password)` - Read data from tag
- `write_data_g2(epc, data, mem, word_ptr, password)` - Write data to tag
- `start_inventory(target)` - Start continuous inventory
- `stop_inventory()` - Stop continuous inventory

#### Utility Methods

- `init_rfid_callback(callback)` - Set callback function for tag detection
- `hex_string_to_bytes(hex_str)` - Convert hex string to bytes
- `bytes_to_hex_string(data)` - Convert bytes to hex string
- `check_crc(hex_str)` - Check CRC of hex string
- `get_available_ports()` - Get list of available serial ports
- `is_port_available(port_name)` - Check if a specific port is available

### RFIDTag Class

Represents an RFID tag with the following attributes:

- `packet_param` - Packet parameter
- `length` - Length of tag data
- `uid` - Unique identifier
- `phase_begin` - Beginning phase
- `phase_end` - Ending phase
- `rssi` - Received Signal Strength Indicator
- `freq_khz` - Frequency in kHz
- `ant` - Antenna number
- `device_name` - Device name

### Error Codes

- `0` - Success
- `48` - Connection error
- `49` - Timeout/CRC error
- `51` - Operation in progress
- `53` - Already connected

### Exceptions

- `UHFReaderError` - Base exception for UHF reader operations
- `ConnectionError` - Raised when connection fails
- `TimeoutError` - Raised when operations timeout
- `ReaderNotConnectedError` - Raised when reader is not connected
- `OperationInProgressError` - Raised when operation is in progress

## Examples

### Example 1: Simple Inventory (Cross-platform)

```python
from PythonSDK import UHFReader

reader = UHFReader()

# Get available ports
available_ports = reader.get_available_ports()
print(f"Available ports: {available_ports}")

# Connect to reader (works on all platforms)
if reader.open_com_port(1, 255, 5) == 0:
    print("Connected!")

    # Set RF power
    reader.set_rf_power(30)

    # Perform inventory
    tags = reader.inventory_g2(scan_time=10)
    print(f"Found {len(tags)} tags:")

    for tag in tags:
        print(f"  EPC: {tag.uid}")
        print(f"  Antenna: {tag.ant}")
        print(f"  RSSI: {tag.rssi}")

    reader.close_com_port()
```

### Example 2: macOS/Linux Specific Port Usage

```python
from PythonSDK import UHFReader

reader = UHFReader()

# List available ports
ports = reader.get_available_ports()
print(f"Available ports: {ports}")

# Connect using specific device path
if reader.open_com_port("/dev/tty.usbserial-10", 255, 5) == 0:
    print("Connected to /dev/tty.usbserial-10!")

    # Your RFID operations here
    tags = reader.inventory_g2(scan_time=5)
    for tag in tags:
        print(f"Tag: {tag.uid}")

    reader.close_com_port()
```

### Example 3: Continuous Monitoring

```python
from PythonSDK import UHFReader, RFIDTag
import time

def on_tag_detected(tag: RFIDTag):
    print(f"[{time.strftime('%H:%M:%S')}] Tag: {tag.uid}")

reader = UHFReader()
reader.init_rfid_callback(on_tag_detected)

if reader.open_com_port(1, 255, 5) == 0:
    print("Starting continuous monitoring...")
    reader.start_inventory()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        reader.stop_inventory()
        reader.close_com_port()
```

### Example 4: Tag Data Operations

```python
from PythonSDK import UHFReader

reader = UHFReader()

if reader.open_com_port(1, 255, 5) == 0:
    # Find a tag
    tags = reader.inventory_g2(scan_time=5)

    if tags:
        tag_epc = tags[0].uid
        print(f"Working with tag: {tag_epc}")

        # Write data
        test_data = b"TestData123"
        if reader.write_data_g2(tag_epc, test_data, mem=3, word_ptr=0) == 0:
            print("Data written successfully")

            # Read data back
            read_data = reader.read_data_g2(tag_epc, mem=3, word_ptr=0, num=6)
            print(f"Read data: {read_data}")

    reader.close_com_port()
```

## Configuration

### Baud Rate Codes

- `0` - 9600 bps
- `1` - 19200 bps
- `2` - 38400 bps
- `5` - 57600 bps
- `6` - 115200 bps

### Memory Banks

- `0` - Reserved memory
- `1` - EPC memory
- `2` - TID memory
- `3` - User memory

### Q Values

Q value affects anti-collision algorithm performance:

- `0-15` - Valid range
- `4` - Default value (good for most applications)

## Troubleshooting

### Common Issues

1. **Connection Failed (Error 48)**

   - Check if the port is correct
   - Verify the reader is powered on
   - Check cable connections
   - Try different baud rates
   - On macOS/Linux, ensure you have proper permissions for the device

2. **No Tags Detected**

   - Check RF power setting
   - Verify tags are within range
   - Check antenna connections
   - Try different Q values

3. **Read/Write Failures**

   - Verify tag EPC is correct
   - Check access password
   - Ensure memory bank and address are valid
   - Verify tag is still in range

4. **Port Not Found (macOS/Linux)**
   - Check if the device is recognized: `ls /dev/tty*`
   - Ensure proper USB drivers are installed
   - Try different device paths (e.g., `/dev/ttyUSB0`, `/dev/ttyACM0`)
   - Check user permissions for the device

### Debug Mode

Enable debug output by setting the log level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Platform-Specific Notes

#### Windows

- Ports are named `COM1`, `COM2`, etc.
- Use port numbers: `reader.open_com_port(1, 255, 5)` for COM1

#### macOS

- Ports are typically named `/dev/tty.usbserial-xxxx` or `/dev/tty.usbmodemxxxx`
- Use device paths or port indices: `reader.open_com_port("/dev/tty.usbserial-10", 255, 5)`

#### Linux

- Ports are typically named `/dev/ttyUSB0`, `/dev/ttyACM0`, etc.
- Use device paths or port indices: `reader.open_com_port("/dev/ttyUSB0", 255, 5)`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:

- Create an issue on GitHub
- Check the documentation
- Review the examples

## Changelog

### Version 1.0.0

- Initial release
- Basic RFID operations
- Serial and TCP connections
- Tag inventory and read/write operations
- Callback support for real-time monitoring
- Cross-platform support (Windows, macOS, Linux)
