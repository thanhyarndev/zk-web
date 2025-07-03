import serial
import time
import threading
from typing import List, Optional, Callable, Dict, Any, Union
from dataclasses import dataclass
import logging
from serial.tools import list_ports
from queue import Queue, Empty

def calculate_crc16(data: bytes) -> int:
    """Calculate CRC16 checksum for RFID commands.

    Parameters:
        data (bytes): Data bytes to calculate CRC for.

    Returns:
        int: 16-bit CRC value.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc

def main():
    NW = serial.Serial('/dev/cu.usbserial-10', 57600, timeout=1)


    if NW:
        try:
            
        #     cmd_data = bytes([0x09, 0x00, 0x01, 0xF4, 0x00, 0x00, 0x80, 0x15])
        #     checksum = calculate_crc16(cmd_data)
        #     full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # # Send command
        #     NW.write(full_command)
        #     NW.flush()
            while 1:
                #if NW.in_waiting > 0:
                    tmp = NW.read(1)
                    print("Received:", ' '.join(f'{b:02X}' for b in tmp))
                    # print(' '.join(f'{b:02X}' for b in tmp))
                    #NW.close()
                    #exit()

        except KeyboardInterrupt:
            print("\nStopping...")
            NW.close()
    else:
        print("Failed to connect to reader")

if __name__ == "__main__":
    main()