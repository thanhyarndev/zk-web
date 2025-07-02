#!/usr/bin/env python3
"""
Read/Write operations demo for UHF RFID Reader Python SDK
"""

import sys
import time
import platform
from pathlib import Path

# Add the parent directory to the path so we can import the SDK
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PythonSDK import UHFReader, RFIDTag

def main():
    """Main function demonstrating read/write operations"""
    print("UHF RFID Reader Python SDK - Read/Write Demo")
    print("=" * 50)
    print(f"Platform: {platform.system()}")
    print()
    
    # Create reader instance
    reader = UHFReader()
    
    # Get available ports
    available_ports = reader.get_available_ports()
    print(f"Available ports: {available_ports}")
    
    if not available_ports:
        print("No serial ports available!")
        return
    
    # Determine port to use based on platform
    port_to_use = None
    
    if platform.system() == "Windows":
        # On Windows, try COM1
        port_to_use = 1
        print(f"Windows detected - trying COM{port_to_use}")
    else:
        # On macOS/Linux, show available ports and try the first one
        print("macOS/Linux detected - available ports:")
        for i, port in enumerate(available_ports, 1):
            print(f"  {i}. {port}")
        
        # Try the first available port
        port_to_use = 1
        print(f"Trying port index {port_to_use} ({available_ports[port_to_use-1]})")
    
    # Connect to reader
    print(f"Connecting to port: {port_to_use}")
    result = reader.open_com_port(port=port_to_use, com_addr=255, baud=5)
    
    if result != 0:
        print(f"Connection failed: {result}")
        if platform.system() != "Windows":
            print(f"\nPlatform-specific troubleshooting:")
            print(f"  - Available ports: {available_ports}")
            print(f"  - Try using a specific device path:")
            if available_ports:
                print(f"    reader.open_com_port('{available_ports[0]}', 255, 5)")
            print(f"  - Check device permissions: ls -l /dev/tty*")
        return
    
    print("✓ Connected successfully!")
    
    try:
        # Set RF power
        reader.set_rf_power(30)
        
        # Find a tag to work with
        print("\nSearching for tags...")
        tags = reader.inventory_g2(scan_time=5)
        
        if not tags:
            print("No tags found! Please place a tag near the reader and try again.")
            return
        
        # Use the first tag found
        target_tag = tags[0]
        print(f"Working with tag: {target_tag.uid}")
        
        # Demo 1: Read existing data
        print("\n" + "=" * 30)
        print("DEMO 1: Reading Existing Data")
        print("=" * 30)
        
        try:
            # Read from user memory (bank 3)
            print("Reading 8 words from user memory...")
            data = reader.read_data_g2(
                epc=target_tag.uid,
                mem=3,  # User memory
                word_ptr=0,  # Start from word 0
                num=8  # Read 8 words (32 bytes)
            )
            
            print(f"Raw data: {data.hex()}")
            
            # Try to interpret as text
            try:
                text_data = data.decode('utf-8', errors='ignore').rstrip('\x00')
                if text_data:
                    print(f"Text data: '{text_data}'")
                else:
                    print("No readable text data found")
            except:
                print("Data is not readable as text")
            
            # Show as 32-bit words
            print("Data as 32-bit words:")
            for i in range(0, len(data), 4):
                word_data = data[i:i+4]
                if len(word_data) == 4:
                    word_int = int.from_bytes(word_data, byteorder='little')
                    print(f"  Word {i//4}: 0x{word_int:08X} ({word_int})")
                else:
                    print(f"  Word {i//4}: {word_data.hex()} (incomplete)")
        
        except Exception as e:
            print(f"Read failed: {e}")
        
        # Demo 2: Write data
        print("\n" + "=" * 30)
        print("DEMO 2: Writing Data")
        print("=" * 30)
        
        # Prepare test data
        test_message = "Hello RFID World!"
        test_data = test_message.encode('utf-8')
        
        # Pad to 32 bytes (8 words)
        padded_data = test_data.ljust(32, b'\x00')
        
        print(f"Writing message: '{test_message}'")
        print(f"Data (hex): {padded_data.hex()}")
        
        try:
            result = reader.write_data_g2(
                epc=target_tag.uid,
                data=padded_data,
                mem=3,  # User memory
                word_ptr=0,  # Start from word 0
                password="00000000"  # Default password
            )
            
            if result == 0:
                print("✓ Write successful!")
                
                # Verify by reading back
                print("\nVerifying write by reading back...")
                verify_data = reader.read_data_g2(
                    epc=target_tag.uid,
                    mem=3,
                    word_ptr=0,
                    num=8
                )
                
                print(f"Read back: {verify_data.hex()}")
                
                # Try to decode as text
                try:
                    verify_text = verify_data.decode('utf-8', errors='ignore').rstrip('\x00')
                    print(f"Text: '{verify_text}'")
                    
                    if verify_text == test_message:
                        print("✓ Verification successful!")
                    else:
                        print("✗ Verification failed - data mismatch")
                
                except:
                    print("Could not decode as text")
            
            else:
                print(f"✗ Write failed with error code: {result}")
        
        except Exception as e:
            print(f"Write failed: {e}")
        
        # Demo 3: Write different data types
        print("\n" + "=" * 30)
        print("DEMO 3: Writing Different Data Types")
        print("=" * 30)
        
        # Write some test values
        test_values = [
            ("Integer", b'\x01\x02\x03\x04'),  # 0x04030201
            ("Float", b'\x00\x00\x80\x3F'),    # 1.0 in IEEE 754
            ("String", b'RFID\x00\x00\x00\x00'),  # "RFID"
        ]
        
        for i, (data_type, data) in enumerate(test_values):
            print(f"\nWriting {data_type} data: {data.hex()}")
            
            try:
                result = reader.write_data_g2(
                    epc=target_tag.uid,
                    data=data,
                    mem=3,
                    word_ptr=i+1,  # Start from word 1
                    password="00000000"
                )
                
                if result == 0:
                    print(f"✓ {data_type} write successful!")
                    
                    # Read back
                    read_data = reader.read_data_g2(
                        epc=target_tag.uid,
                        mem=3,
                        word_ptr=i+1,
                        num=1
                    )
                    
                    print(f"  Read back: {read_data.hex()}")
                    
                    # Interpret based on type
                    if data_type == "Integer":
                        value = int.from_bytes(read_data[:4], byteorder='little')
                        print(f"  As integer: {value}")
                    elif data_type == "Float":
                        import struct
                        try:
                            value = struct.unpack('<f', read_data[:4])[0]
                            print(f"  As float: {value}")
                        except:
                            print(f"  Could not interpret as float")
                    elif data_type == "String":
                        try:
                            value = read_data.decode('utf-8', errors='ignore').rstrip('\x00')
                            print(f"  As string: '{value}'")
                        except:
                            print(f"  Could not interpret as string")
                
                else:
                    print(f"✗ {data_type} write failed: {result}")
            
            except Exception as e:
                print(f"✗ {data_type} write failed: {e}")
        
        # Demo 4: Read from different memory banks
        print("\n" + "=" * 30)
        print("DEMO 4: Reading from Different Memory Banks")
        print("=" * 30)
        
        memory_banks = [
            (1, "EPC Memory"),
            (2, "TID Memory"),
            (3, "User Memory")
        ]
        
        for bank_id, bank_name in memory_banks:
            print(f"\nReading from {bank_name} (Bank {bank_id}):")
            
            try:
                data = reader.read_data_g2(
                    epc=target_tag.uid,
                    mem=bank_id,
                    word_ptr=0,
                    num=4  # Read 4 words
                )
                
                print(f"  Data: {data.hex()}")
                
                # Try to interpret EPC memory
                if bank_id == 1:  # EPC memory
                    try:
                        # EPC memory typically contains the EPC code
                        epc_length = data[0] if data else 0
                        if epc_length > 0 and epc_length <= len(data) - 1:
                            epc_data = data[1:1+epc_length]
                            print(f"  EPC: {epc_data.hex()}")
                    except:
                        pass
                
                # Try to interpret TID memory
                elif bank_id == 2:  # TID memory
                    try:
                        # TID memory contains manufacturer information
                        tid_text = data.decode('ascii', errors='ignore').rstrip('\x00')
                        if tid_text:
                            print(f"  TID: '{tid_text}'")
                    except:
                        pass
            
            except Exception as e:
                print(f"  Read failed: {e}")
    
    except Exception as e:
        print(f"Unexpected error: {e}")
    
    finally:
        # Close connection
        print("\nClosing connection...")
        reader.close_com_port()
        print("✓ Connection closed")

if __name__ == "__main__":
    main() 