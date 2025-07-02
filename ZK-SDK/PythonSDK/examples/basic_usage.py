#!/usr/bin/env python3
"""
UHF RFID Reader Console Control App (User-Friendly)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from PythonSDK import UHFReader, RFIDTag, UHFReaderError

def print_menu():
    print("\n==== UHF RFID Reader Control App ====")
    print("1. Connect to Reader (Serial)")
    print("2. Connect to Reader (TCP)")
    print("3. Disconnect Reader")
    print("4. Show Available Serial Ports")
    print("5. Get Reader Information")
    print("6. Inventory (Scan Tags)")
    print("7. Read Data from Tag")
    print("8. Write Data to Tag")
    print("9. Set RF Power (dBm)")
    print("10. Get RF Power (dBm)")
    print("11. Buzzer and LED Control")
    print("12. Set Antenna (1-4)")
    print("13. Get Antenna Power (dBm)")
    print("14. Set Inventory Scan Time (ms)")
    print("0. Exit")
    print("====================================")

def prompt_int(prompt, default=None, minval=None, maxval=None):
    while True:
        val = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
        if not val and default is not None:
            return default
        try:
            ival = int(val)
            if minval is not None and ival < minval:
                print(f"Value must be >= {minval}")
                continue
            if maxval is not None and ival > maxval:
                print(f"Value must be <= {maxval}")
                continue
            return ival
        except Exception:
            print("Please enter a valid decimal number.")

def prompt_str(prompt, default=None):
    val = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
    return val if val else default

def main():
    reader = UHFReader()
    connected = False
    tags = []
    port_to_use = None
    print("Welcome to the UHF RFID Reader Console App!")
    while True:
        print_menu()
        choice = input("Select an option: ").strip()
        try:
            if choice == "1":
                # Connect to Reader (Serial)
                available_ports = reader.get_available_ports()
                print(f"Available serial ports: {available_ports}")
                if not available_ports:
                    print("No serial ports available!")
                    continue
                for i, port in enumerate(available_ports, 1):
                    print(f"  {i}. {port}")
                idx = prompt_int(f"Select port [1-{len(available_ports)}]", 1, 1, len(available_ports)) - 1
                port_to_use = available_ports[idx]
                print("Baud rate options:")
                print("  0 = 9600 bps")
                print("  1 = 19200 bps")
                print("  2 = 38400 bps")
                print("  5 = 57600 bps")
                print("  6 = 115200 bps")
                baud = prompt_int("Enter baud rate code", 5, 0, 6)
                result = reader.open_com_port(port=port_to_use, com_addr=255, baud=baud)
                if result == 0:
                    print("✓ Connected successfully via serial port!")
                    connected = True
                else:
                    print(f"✗ Connection failed: error code {result}")
            elif choice == "2":
                # Connect to Reader (TCP)
                ip = prompt_str("Enter reader IP address", "192.168.1.100")
                port = prompt_int("Enter TCP port", 8080, 1, 65535)
                result = reader.open_net_port(port=port, ip_addr=ip, com_addr=255)
                if result == 0:
                    print("✓ Connected successfully via TCP!")
                    connected = True
                else:
                    print(f"✗ TCP connection failed: error code {result}")
            elif choice == "3":
                # Disconnect
                if not connected:
                    print("Not connected.")
                    continue
                reader.close_com_port()
                reader.close_net_port()
                connected = False
                print("Disconnected.")
            elif choice == "4":
                # Show available serial ports
                available_ports = reader.get_available_ports()
                print(f"Available serial ports: {available_ports}")
            elif choice == "5":
                # Get Reader Information
                if not connected:
                    print("Not connected.")
                    continue
                info = reader.get_reader_information()
                print("Reader Information:")
                for k, v in info.items():
                    print(f"  {k}: {v}")
            elif choice == "6":
                # Inventory (Scan Tags)
                if not connected:
                    print("Not connected.")
                    continue
                scan_time = prompt_int("Enter scan time in ms (e.g. 200)", 200, 10, 2000)
                # Convert ms to 10ms units for SDK
                scan_time_units = max(1, scan_time // 10)
                tags = reader.inventory_g2(scan_time=scan_time_units)
                if tags:
                    print(f"Found {len(tags)} tag(s):")
                    for i, tag in enumerate(tags, 1):
                        print(f"  {i}. EPC: {tag.uid} | Antenna: {tag.ant} | RSSI: {tag.rssi}")
                else:
                    print("No tags found.")
            elif choice == "7":
                # Read Data from Tag
                if not connected:
                    print("Not connected.")
                    continue
                if not tags:
                    print("No tags in memory. Run inventory first.")
                    continue
                for i, tag in enumerate(tags, 1):
                    print(f"  {i}. EPC: {tag.uid}")
                idx = prompt_int(f"Select tag [1-{len(tags)}]", 1, 1, len(tags)) - 1
                tag = tags[idx]
                print("Memory bank options:")
                print("  0 = Reserved")
                print("  1 = EPC")
                print("  2 = TID")
                print("  3 = User")
                mem = prompt_int("Memory bank", 1, 0, 3)
                word_ptr = prompt_int("Word pointer", 0, 0)
                num = prompt_int("Number of words", 4, 1)
                pwd = prompt_str("Password (8 hex chars)", "00000000")
                try:
                    data = reader.read_data_g2(epc=tag.uid, mem=mem, word_ptr=word_ptr, num=num, password=pwd)
                    print(f"Read data: {data.hex().upper()}")
                except Exception as e:
                    print(f"Read failed: {e}")
            elif choice == "8":
                # Write Data to Tag
                if not connected:
                    print("Not connected.")
                    continue
                if not tags:
                    print("No tags in memory. Run inventory first.")
                    continue
                for i, tag in enumerate(tags, 1):
                    print(f"  {i}. EPC: {tag.uid}")
                idx = prompt_int(f"Select tag [1-{len(tags)}]", 1, 1, len(tags)) - 1
                tag = tags[idx]
                print("Memory bank options:")
                print("  0 = Reserved")
                print("  1 = EPC")
                print("  2 = TID")
                print("  3 = User")
                mem = prompt_int("Memory bank", 1, 0, 3)
                word_ptr = prompt_int("Word pointer", 0, 0)
                data_hex = prompt_str("Data to write (hex, e.g. 01020304)")
                pwd = prompt_str("Password (8 hex chars)", "00000000")
                try:
                    data = bytes.fromhex(data_hex)
                except Exception:
                    print("Invalid hex data.")
                    continue
                try:
                    result = reader.write_data_g2(epc=tag.uid, data=data, mem=mem, word_ptr=word_ptr, password=pwd)
                    print(f"Write result: {result}")
                except Exception as e:
                    print(f"Write failed: {e}")
            elif choice == "9":
                # Set RF Power
                if not connected:
                    print("Not connected.")
                    continue
                power = prompt_int("Enter RF Power (dBm, 0-30)", 20, 0, 30)
                result = reader.set_rf_power(power)
                print(f"Set RF Power result: {result}")
            elif choice == "10":
                # Get RF Power
                if not connected:
                    print("Not connected.")
                    continue
                try:
                    power = reader.read_rf_power()
                    print(f"Current RF Power: {power} dBm")
                except Exception as e:
                    print(f"Failed to get RF Power: {e}")
            elif choice == "11":
                # Buzzer and LED Control
                if not connected:
                    print("Not connected.")
                    continue
                active = prompt_int("Active time (ms)", 10, 1)
                silent = prompt_int("Silent time (ms)", 10, 0)
                times = prompt_int("Number of beeps", 1, 1)
                result = reader.buzzer_and_led_control(active, silent, times)
                print(f"Buzzer/LED result: {result}")
            elif choice == "12":
                # Set Antenna
                if not connected:
                    print("Not connected.")
                    continue
                ant = prompt_int("Antenna number (1-4)", 1, 1, 4)
                result = reader.set_antenna_multiplexing(ant)
                print(f"Set Antenna result: {result}")
            elif choice == "13":
                # Get Antenna Power
                if not connected:
                    print("Not connected.")
                    continue
                try:
                    power_bytes = reader.get_antenna_power()
                    if power_bytes:
                        print("Antenna Power Settings:")
                        for i, power in enumerate(power_bytes, 1):
                            print(f"  Antenna {i}: {power} dBm")
                    else:
                        print("Failed to get antenna power")
                except Exception as e:
                    print(f"Failed to get antenna power: {e}")
            elif choice == "14":
                # Set Inventory Scan Time
                if not connected:
                    print("Not connected.")
                    continue
                scan_time = prompt_int("Scan time in ms (10-2000)", 200, 10, 2000)
                scan_time_units = max(1, scan_time // 10)
                result = reader.set_inventory_scan_time(scan_time_units)
                print(f"Set Inventory Scan Time result: {result}")
            elif choice == "0":
                if connected:
                    reader.close_com_port()
                    reader.close_net_port()
                print("Goodbye!")
                break
            else:
                print("Invalid option.")
        except Exception as e:
            print(f"Error: {e}")
            continue

if __name__ == "__main__":
    main() 