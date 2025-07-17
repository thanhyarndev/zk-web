"""
Core Reader class for low-level communication with UHF RFID readers
"""

import socket
import serial
import serial.tools.list_ports
import struct
import time
import threading
from typing import Optional, Callable, List, Tuple, Dict, Any
from rfid_tag import RFIDTag
from exceptions import ConnectionError, TimeoutError, UHFReaderError
import platform

class Reader:
    """
    Low-level reader class that handles communication with UHF RFID readers
    via serial (COM) and network (TCP) connections.
    """
    
    # CRC polynomial and preset value
    POLYNOMIAL = 0x8408  # 33800 in decimal
    PRESET_VALUE = 0xFFFF
    
    # Connection types
    CONNECTION_NONE = -1
    CONNECTION_SERIAL = 0
    CONNECTION_TCP = 1
    
    def __init__(self):
        """Initialize the reader"""
        self.receive_callback: Optional[Callable[[RFIDTag], None]] = None
        self.recv_callback: Optional[Callable[[bytes], None]] = None
        self.send_callback: Optional[Callable[[bytes], None]] = None
        
        # Serial connection
        self.serial_port: Optional[serial.Serial] = None
        
        # TCP connection
        self.tcp_client: Optional[socket.socket] = None
        self.tcp_stream = None
        
        # Connection state
        self.connection_type = self.CONNECTION_NONE
        self.device_name = ""
        self.com_addr = 0
        self.inventory_scan_time = 0
        
        # Buffers
        self.recv_buffer = bytearray(8000)
        self.send_buffer = bytearray(300)
        self.recv_length = 0
        self.buffer = bytearray(4096)  # Simulate device buffer (should be filled by device read logic)
    
    def _get_crc(self, data: bytes, data_len: int) -> bytes:
        """Calculate CRC for the given data"""
        crc = self.PRESET_VALUE
        
        for i in range(data_len):
            crc ^= data[i]
            for j in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ self.POLYNOMIAL
                else:
                    crc >>= 1
        
        return struct.pack('<H', crc)
    
    def _check_crc(self, data: bytes, length: int) -> int:
        """Check CRC of received data"""
        if length < 2:
            return 49  # Invalid data
        
        # Extract data without CRC
        data_without_crc = data[:length-2]
        
        # Calculate expected CRC
        expected_crc = self._get_crc(data_without_crc, len(data_without_crc))
        
        # Compare with received CRC
        received_crc = data[length-2:length]
        
        if expected_crc == received_crc:
            return 0  # Success
        else:
            return 49  # CRC error
    
    def _hex_string_to_bytes(self, hex_str: str) -> bytes:
        """Convert hex string to bytes"""
        hex_str = hex_str.replace(" ", "")
        return bytes.fromhex(hex_str)
    
    def _bytes_to_hex_string(self, data: bytes) -> str:
        """Convert bytes to hex string"""
        return data.hex().upper()
    
    def _bytes_to_hex_string_spaced(self, data: bytes) -> str:
        """Convert bytes to hex string with spaces"""
        return ' '.join(f'{b:02X}' for b in data)
    
    def _open_serial(self, port, baud_rate: int) -> int:
        """Open serial connection. Accepts int (Windows) or str (device path) for port."""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            
            # Map baud rate codes to actual baud rates
            baud_map = {
                0: 9600,
                1: 19200,
                2: 38400,
                5: 57600,
                6: 115200
            }
            actual_baud = baud_map.get(baud_rate, 57600)
            
            # Determine port name
            port_name = None
            if isinstance(port, int):
                if platform.system() == "Windows":
                    port_name = f"COM{port}"
                else:
                    # On macOS/Linux, map 1 -> first available port, 2 -> second, etc.
                    ports = list(serial.tools.list_ports.comports())
                    if 0 < port <= len(ports):
                        port_name = ports[port-1].device
                    else:
                        raise ValueError(f"Port index {port} is out of range. Available: {[p.device for p in ports]}")
            elif isinstance(port, str):
                port_name = port
            else:
                raise ValueError("Port must be an int (index) or str (device path)")
            
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=actual_baud,
                timeout=0.2,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            
            self.device_name = port_name
            return 0
            
        except Exception as e:
            print(f"Serial connection error: {e}")
            return 48  # Connection error
    
    def open_by_com(self, port, com_addr: int, baud: int, skip_verification: bool = False) -> int:
        """Open connection via COM port. Accepts int (index) or str (device path) for port."""
        if self._open_serial(port, baud) == 0:
            self.connection_type = self.CONNECTION_SERIAL
            
            if skip_verification:
                # Skip reader verification for testing
                self.com_addr = com_addr
                return 0
            
            # Get reader information to verify connection
            version_info = bytearray(2)
            reader_type = [0]
            tr_type = [0]
            dmax_fre = [0]
            dmin_fre = [0]
            power_dbm = [0]
            scan_time = [0]
            ant = [0]
            beep_en = [0]
            output_rep = [0]
            check_ant = [0]
            
            result = self.get_reader_information(
                com_addr, version_info, reader_type, tr_type,
                dmax_fre, dmin_fre, power_dbm, scan_time,
                ant, beep_en, output_rep, check_ant
            )
            
            if result == 0:
                self.com_addr = com_addr
                return 0
            else:
                self.serial_port.close()
                self.connection_type = self.CONNECTION_NONE
                return 48
        
        return 48
    
    def close_by_com(self) -> int:
        """Close COM connection"""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                self.connection_type = self.CONNECTION_NONE
                return 0
            return 48
        except Exception as e:
            print(f"Error closing COM connection: {e}")
            return 48
    
    def _open_network(self, ip_addr: str, port: int) -> int:
        """Open network connection"""
        try:
            self.tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_client.settimeout(2.0)
            self.tcp_client.connect((ip_addr, port))
            self.tcp_stream = self.tcp_client.makefile('rwb')
            return 0
        except Exception as e:
            print(f"Network connection error: {e}")
            return 48
    
    def open_by_tcp(self, ip_addr: str, port: int, com_addr: int) -> int:
        """Open connection via TCP"""
        if self._open_network(ip_addr, port) == 0:
            self.connection_type = self.CONNECTION_TCP
            
            # Get reader information to verify connection
            version_info = bytearray(2)
            reader_type = [0]
            tr_type = [0]
            dmax_fre = [0]
            dmin_fre = [0]
            power_dbm = [0]
            scan_time = [0]
            ant = [0]
            beep_en = [0]
            output_rep = [0]
            check_ant = [0]
            
            result = self.get_reader_information(
                com_addr, version_info, reader_type, tr_type,
                dmax_fre, dmin_fre, power_dbm, scan_time,
                ant, beep_en, output_rep, check_ant
            )
            
            if result == 0:
                self.com_addr = com_addr
                self.device_name = f"{ip_addr}:{port}"
                return 0
            else:
                self.tcp_client.close()
                self.connection_type = self.CONNECTION_NONE
                return 48
        
        return 48
    
    def close_by_tcp(self) -> int:
        """Close TCP connection"""
        try:
            if self.tcp_client:
                self.tcp_client.close()
                self.connection_type = self.CONNECTION_NONE
                return 0
            return 48
        except Exception as e:
            print(f"Error closing TCP connection: {e}")
            return 48
    
    def _send_data(self, data: bytes, bytes_to_send: int) -> int:
        """Send data to the connected port (clears buffers before sending)"""
        try:
            if self.connection_type == self.CONNECTION_SERIAL:
                if self.serial_port and self.serial_port.is_open:
                    # Clear buffers before sending (like C# SendDataToPort)
                    self.serial_port.reset_input_buffer()
                    self.serial_port.reset_output_buffer()
                    self.serial_port.write(data[:bytes_to_send])
                    self.serial_port.flush()
                    return 0
            elif self.connection_type == self.CONNECTION_TCP:
                if self.tcp_client:
                    self.tcp_client.send(data[:bytes_to_send])
                    return 0
            
            return 48
        except Exception as e:
            print(f"Send data error: {e}")
            return 48

    def _send_data_noclear(self, data: bytes, bytes_to_send: int) -> int:
        """Send data to the connected port (does NOT clear buffers before sending - like C# SendDataToPort_Noclear)"""
        try:
            if self.connection_type == self.CONNECTION_SERIAL:
                if self.serial_port and self.serial_port.is_open:
                    # Do NOT clear buffers before sending (like C# SendDataToPort_Noclear)
                    self.serial_port.write(data[:bytes_to_send])
                    self.serial_port.flush()
                    return 0
            elif self.connection_type == self.CONNECTION_TCP:
                if self.tcp_client:
                    self.tcp_client.send(data[:bytes_to_send])
                    return 0
            
            return 48
        except Exception as e:
            print(f"Send data error: {e}")
            return 48
    
    def _get_data_from_port(self, cmd: int, end_time: int) -> int:
        """Get data from port with timeout - exact C# GetDataFromPort implementation"""
        num = 0  # num2 in C# (buffer position)
        array = bytearray(2000)  # array in C# (main buffer)
        num2 = 0  # num2 in C# (remaining bytes from previous read)
        num3 = int(time.time() * 1000)  # num3 in C# (Environment.TickCount equivalent)
        
        print(f"[DEBUG] _get_data_from_port: cmd=0x{cmd:02X}, end_time={end_time}ms")
        
        try:
            while int(time.time() * 1000) - num3 < end_time:
                array2 = self.read_data_from_port()  # array2 in C# (ReadDataFromPort)
                if array2 is None:
                    continue
                
                num = len(array2)  # num in C# (array2.Length)
                if num == 0:
                    continue
                
                print(f"[DEBUG] _get_data_from_port: read {num} bytes: {array2.hex()}")
                
                # array3 = new byte[num + num2] (combine previous and new data)
                array3 = bytearray(num + num2)
                # Array.Copy(array, 0, array3, 0, num2)
                array3[0:num2] = array[0:num2]
                # Array.Copy(array2, 0, array3, num2, num)
                array3[num2:num2+num] = array2
                
                num4 = 0  # num4 in C# (position in array3)
                while len(array3) - num4 > 4:
                    # Check for valid packet header: (array3[num4] >= 4 && array3[num4 + 2] == cmd) || (array3[num4] == 5 && array3[num4 + 2] == 0)
                    if ((array3[num4] >= 4 and array3[num4 + 2] == cmd) or 
                        (array3[num4] == 5 and array3[num4 + 2] == 0)):
                        
                        num5 = array3[num4]  # num5 in C# (packet length)
                        if len(array3) < num4 + num5 + 1:
                            break  # Not enough data for complete packet
                        
                        # array4 = new byte[num5 + 1] (extract complete packet)
                        array4 = bytearray(num5 + 1)
                        # Array.Copy(array3, num4, array4, 0, array4.Length)
                        array4[0:num5+1] = array3[num4:num4+num5+1]
                        
                        print(f"[DEBUG] _get_data_from_port: checking packet: {array4.hex()}")
                        
                        # CheckCRC(array4, array4.Length) == 0
                        if self._check_crc(array4, len(array4)) == 0:
                            # Array.Copy(array4, 0, RecvBuff, 0, array4.Length)
                            self.recv_buffer[0:len(array4)] = array4
                            self.recv_length = len(array4)
                            print(f"[DEBUG] _get_data_from_port: valid packet found, length={self.recv_length}")
                            return 0  # Success
                        
                        num4 += 1
                    else:
                        num4 += 1
                
                # Handle remaining data: if (array3.Length > num4)
                if len(array3) > num4:
                    num2 = len(array3) - num4  # num2 = array3.Length - num4
                    # Array.Copy(array3, num4, array, 0, num2)
                    array[0:num2] = array3[num4:num4+num2]
                else:
                    num2 = 0
                
                print(f"[DEBUG] _get_data_from_port: remaining bytes: {num2}")
        
        except Exception as ex:
            print(f"[DEBUG] _get_data_from_port: exception: {ex}")
            # ex.ToString() in C# - just log the exception
        
        print(f"[DEBUG] _get_data_from_port: timeout after {end_time}ms")
        return 48  # Return 48 (timeout) like C#
    
    def get_reader_information(self, com_addr: int, version_info: bytearray,
                             reader_type: list, tr_type: list, dmax_fre: list,
                             dmin_fre: list, power_dbm: list, scan_time: list,
                             ant: list, beep_en: list, output_rep: list,
                             check_ant: list) -> int:
        """Get reader information"""
        # Command format: [Length][ComAddr][Command][CRC_Low][CRC_High]
        # Command 0x21 = GetReaderInformation
        cmd = bytearray([4, com_addr, 0x21])  # Length=4, ComAddr, Command=0x21
        
        # Add CRC
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        
        # Wait for response
        result = self._get_data_from_port(0x21, 1500)
        if result != 0:
            return result
        
        # Parse response
        if self.recv_length >= 16:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                return 49
            
            # Check command response
            if self.recv_buffer[2] == 0x21 and self.recv_buffer[3] == 0:
                # Extract information from response
                com_addr = self.recv_buffer[1]
                version_info[0:2] = self.recv_buffer[4:6]
                reader_type[0] = self.recv_buffer[6]
                tr_type[0] = self.recv_buffer[7]
                dmax_fre[0] = self.recv_buffer[8]
                dmin_fre[0] = self.recv_buffer[9]
                power_dbm[0] = self.recv_buffer[10]
                scan_time[0] = self.recv_buffer[11]
                self.inventory_scan_time = self.recv_buffer[11]  # Set inventory scan time like C# SDK
                ant[0] = self.recv_buffer[12]
                beep_en[0] = self.recv_buffer[13]
                output_rep[0] = self.recv_buffer[14]
                check_ant[0] = self.recv_buffer[15]
                return 0
            else:
                return self.recv_buffer[3] if self.recv_buffer[2] == 0x21 else 49
        
        return 49
    
    def _get_inventory_g1(self, scan_time: int, epc_list: bytearray, ant: list, total_len: list, card_num: list, cmd: int, rssi_list: list = None) -> int:
        epcNum = 0
        dlen = 0
        num = 0
        array = bytearray(4096)
        num2 = 0
        start_tick = int(time.time() * 1000)
        last_packet_tick = start_tick
        timeout_ms = scan_time * 2 + 2000

        try:
            while int(time.time() * 1000) - last_packet_tick < timeout_ms:
                array2 = self.read_data_from_port()
                if array2 is not None:
                    num = len(array2)
                    if num == 0:
                        continue
                    array3 = bytearray(num2 + num)
                    array3[:num2] = array[:num2]
                    array3[num2:num2+num] = array2
                    num4 = 0
                    while len(array3) - num4 > 5:
                        if array3[num4] >= 5 and array3[num4 + 2] == cmd:
                            num5 = array3[num4]
                            if len(array3) < num4 + num5 + 1:
                                break
                            array4 = array3[num4:num4+num5+1]
                            if self._check_crc(array4, len(array4)) == 0:
                                last_packet_tick = int(time.time() * 1000)
                                num7 = array4[3]
                                if num7 in (1, 2, 3, 4):
                                    num8 = array4[5]
                                    if num8 > 0:
                                        num9 = 6
                                        for i in range(num8):
                                            num10 = array4[num9] & 0x3F
                                            flag = (array4[num9] & 0x40) > 0
                                            phase_begin = phase_end = freqkhz = 0
                                            if not flag:
                                                epc_list[dlen:dlen+num10+2] = array4[num9:num9+num10+2]
                                                dlen += num10 + 2
                                            else:
                                                epc_list[dlen:dlen+num10+6] = array4[num9:num9+num10+6]
                                                # Extract phase/freq as in C#
                                                phase_begin = array4[num9+num10+2] * 256 + array4[num9+num10+3]
                                                phase_end = array4[num9+num10+4] * 256 + array4[num9+num10+5]
                                                freqkhz = (array4[num9+num10+6] << 16) + (array4[num9+num10+7] << 8) + array4[num9+num10+8]
                                                dlen += num10 + 9
                                            epcNum += 1
                                            ant[0] = array4[4]
                                            # Call callback if available
                                            if self.receive_callback:
                                                tag = RFIDTag()
                                                tag.device_name = getattr(self, 'dev_name', 'Unknown')
                                                tag.antenna = array4[4]
                                                tag.len = array4[num9]
                                                tag.phase_begin = phase_begin
                                                tag.phase_end = phase_end
                                                tag.packet_param = 0
                                                tag.rssi = array4[num9 + 1 + num10]
                                                tag.freqkhz = freqkhz
                                                tag.epc = self._bytes_to_hex_string(array4[num9+1:num9+1+num10])
                                                self.receive_callback(tag)
                                            num9 = num9 + (9 + num10 if flag else 2 + num10)
                                if num7 != 3:
                                    total_len[0] = dlen
                                    card_num[0] = epcNum
                                    return num7
                                num4 += array4[0] + 1
                            else:
                                num4 += 1
                        else:
                            num4 += 1
                    if len(array3) > num4:
                        num2 = len(array3) - num4
                        array[:num2] = array3[num4:num4+num2]
                    else:
                        num2 = 0
                else:
                    time.sleep(0.001)
        except Exception as ex:
            print(f"[DEBUG] Exception: {ex}")
        total_len[0] = dlen
        card_num[0] = epcNum
        return 48

    def inventory_g2(self, com_addr: bytearray, q_value: bytes, session: bytes,
                    mask_mem: bytes, mask_addr: bytearray, mask_len: bytes,
                    mask_data: bytearray, mask_flag: bytes, addr_tid: bytes,
                    len_tid: bytes, tid_flag: bytes, target: bytes, in_ant: bytes,
                    scan_time: bytes, fast_flag: bytes, epc_list: bytearray,
                    ant: list, total_len: list, card_num: list, rssi_list: list = None) -> int:
        """Perform Gen2 inventory operation (C# SDK logic)"""
        # C# SDK defaults scan_time to 20 if 0 is passed
        scan_time_val = scan_time[0] if scan_time[0] != 0 else 20
        print(f"[DEBUG] Inventory parameters: com_addr={com_addr[0]}, q_value={q_value[0]}, session={session[0]}, scan_time={scan_time_val}")
        
        # Build command exactly like C# SDK
        cmd = bytearray()
        cmd.append(com_addr[0])  # SendBuff[1]
        cmd.append(1)            # SendBuff[2] = command code
        cmd.append(q_value[0])   # SendBuff[3]
        cmd.append(session[0])   # SendBuff[4]
        
        if mask_flag[0] == 1:
            cmd.append(mask_mem[0])  # SendBuff[5]
            cmd.extend(mask_addr)    # SendBuff[6,7]
            cmd.append(mask_len[0])  # SendBuff[8]
            num_bytes = (mask_len[0] + 7) // 8  # Same calculation as C#
            cmd.extend(mask_data[:num_bytes])
            
            if tid_flag[0] == 1:
                if fast_flag[0] == 1:
                    cmd.append(addr_tid[0])
                    cmd.append(len_tid[0])
                    cmd.append(target[0])
                    cmd.append(in_ant[0])
                    cmd.append(scan_time_val)
                    # SendBuff[0] = 15 + num
                    cmd.insert(0, 15 + num_bytes)
                else:
                    cmd.append(addr_tid[0])
                    cmd.append(len_tid[0])
                    # SendBuff[0] = 12 + num
                    cmd.insert(0, 12 + num_bytes)
            elif fast_flag[0] == 1:
                cmd.append(target[0])
                cmd.append(in_ant[0])
                cmd.append(scan_time_val)
                # SendBuff[0] = 13 + num
                cmd.insert(0, 13 + num_bytes)
            else:
                # SendBuff[0] = 10 + num
                cmd.insert(0, 10 + num_bytes)
        elif tid_flag[0] == 1:
            if fast_flag[0] == 1:
                cmd.append(addr_tid[0])
                cmd.append(len_tid[0])
                cmd.append(target[0])
                cmd.append(in_ant[0])
                cmd.append(scan_time_val)
                cmd.insert(0, 11)  # SendBuff[0] = 11
            else:
                cmd.append(addr_tid[0])
                cmd.append(len_tid[0])
                cmd.insert(0, 8)   # SendBuff[0] = 8
        elif fast_flag[0] == 1:
            cmd.append(target[0])
            cmd.append(in_ant[0])
            cmd.append(scan_time_val)
            cmd.insert(0, 9)       # SendBuff[0] = 9
        else:
            cmd.insert(0, 6)       # SendBuff[0] = 6
        
        print(f"[DEBUG] Command before CRC: {cmd.hex()}")
        print(f"[DEBUG] Command length: {cmd[0]}")
        
        # Add CRC - C# uses GetCRC(SendBuff, SendBuff[0] - 1)
        crc = self._get_crc(cmd, cmd[0] - 1)
        cmd.extend(crc)
        
        print(f"[DEBUG] Full command with CRC: {cmd.hex()}")
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            print(f"[DEBUG] Send failed: {result}")
            return result
        
        # C# calls GetInventoryG1(Scantime * 100, ...) - scan_time is in 10ms units
        # So scan_time=20 means 2000ms timeout
        return self._get_inventory_g1(scan_time_val * 100, epc_list, ant, total_len, card_num, 1, rssi_list)
    
    def read_data_g2(self, com_addr: int, epc: bytes, e_num: int,
                    mem: int, word_ptr: int, num: int, password: bytes,
                    mask_mem: int, mask_addr: bytes, mask_len: int,
                    mask_data: bytes, data: bytearray, error_code: list) -> int:
        """Read data from Gen2 tag (C# SDK format)"""
        # Command format: [Length][ComAddr][Command][Data...][CRC_Low][CRC_High]
        # Command 2 = ReadData_G2
        cmd = bytearray()
        cmd.append(com_addr)  # SendBuff[1]
        cmd.append(2)         # SendBuff[2] = command code 2
        cmd.append(e_num)     # SendBuff[3] = EPC length
        
        if e_num == 255:
            # Special case for EPC length 255
            cmd.append(mem)       # SendBuff[4]
            cmd.append(word_ptr)  # SendBuff[5]
            cmd.append(num)       # SendBuff[6]
            cmd.extend(password)  # SendBuff[7-10]
            cmd.append(mask_mem)  # SendBuff[11]
            cmd.extend(mask_addr) # SendBuff[12-13]
            cmd.append(mask_len)  # SendBuff[14]
            num_bytes = (mask_len + 7) // 8 if mask_len % 8 != 0 else mask_len // 8
            cmd.extend(mask_data[:num_bytes])
            # SendBuff[0] = 16 + num_bytes (C# SDK)
            total_len = 16 + num_bytes
        else:
            # Normal case: EPC length 0-31
            cmd.extend(epc)       # SendBuff[4...] = EPC data
            cmd.append(mem)       # SendBuff[ENum*2+4]
            cmd.append(word_ptr)  # SendBuff[ENum*2+5]
            cmd.append(num)       # SendBuff[ENum*2+6]
            cmd.extend(password)  # SendBuff[ENum*2+7...]
            # SendBuff[0] = ENum * 2 + 12 (C# SDK)
            total_len = e_num * 2 + 12
            
            # Add padding to ensure the array has the correct length
            while len(cmd) < total_len - 1:  # -1 because we'll add the length byte
                cmd.append(0)
        
        # Insert length at the beginning
        cmd.insert(0, total_len)
        
        print(f"[DEBUG] Read command before CRC: {cmd.hex()}")
        print(f"[DEBUG] Read command length: {cmd[0]}")
        print(f"[DEBUG] Command array length: {len(cmd)}")
        print(f"[DEBUG] Expected length: {total_len}")
        
        # Add CRC - C# uses GetCRC(SendBuff, SendBuff[0] - 1)
        try:
            crc = self._get_crc(cmd, cmd[0] - 1)
            cmd.extend(crc)
            print(f"[DEBUG] Full read command with CRC: {cmd.hex()}")
        except Exception as e:
            print(f"[DEBUG] CRC calculation error: {e}")
            return 49
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            print(f"[DEBUG] Read send failed: {result}")
            return result
        
        # Wait for response - C# uses GetDataFromPort(2, 3000)
        result = self._get_data_from_port(2, 3000)
        if result != 0:
            print(f"[DEBUG] Read response timeout: {result}")
            return result
        
        print(f"[DEBUG] Read response received: {self.recv_buffer[:self.recv_length].hex()}")
        
        # Parse response
        if self.recv_length >= 4:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                print("[DEBUG] Read response CRC check failed")
                return 49
            
            # Check command response
            if self.recv_buffer[2] == 2:
                status = self.recv_buffer[3]
                print(f"[DEBUG] Read status: {status}")
                if status == 0:
                    # Success - extract data
                    data_len = self.recv_length - 6  # Total - header - CRC
                    if data_len > 0:
                        data[0:data_len] = self.recv_buffer[4:4+data_len]
                        print(f"[DEBUG] Read data extracted: {data[:data_len].hex()}")
                    error_code[0] = 0
                    return 0
                elif status == 252:
                    # Error with error code
                    error_code[0] = self.recv_buffer[4]
                    print(f"[DEBUG] Read error code: {error_code[0]}")
                    return status
                else:
                    return status
            else:
                print(f"[DEBUG] Read response command mismatch: expected 2, got {self.recv_buffer[2]}")
                return 49
        
        return 49
    
    def write_data_g2(self, com_addr: int, epc: bytes, w_num: int,
                     e_num: int, mem: int, word_ptr: int, wdt: bytes,
                     password: bytes, mask_mem: int, mask_addr: bytes,
                     mask_len: int, mask_data: bytes, error_code: int) -> int:
        """Write data to Gen2 tag (C# SDK format)"""
        # Command format: [Length][ComAddr][Command][WNum][ENum][Data...][CRC_Low][CRC_High]
        # Command 3 = WriteData_G2
        cmd = bytearray()
        cmd.append(com_addr)  # SendBuff[1]
        cmd.append(3)         # SendBuff[2] = command code 3
        cmd.append(w_num)     # SendBuff[3]
        cmd.append(e_num)     # SendBuff[4]
        
        if e_num == 255:
            # Special case for EPC length 255
            cmd.append(mem)       # SendBuff[5]
            cmd.append(word_ptr)  # SendBuff[6]
            cmd.extend(wdt)       # SendBuff[7...] = WNum * 2 bytes
            cmd.extend(password)  # SendBuff[7 + WNum*2...] = 4 bytes
            cmd.append(mask_mem)  # SendBuff[11 + WNum*2]
            cmd.extend(mask_addr) # SendBuff[12 + WNum*2, 13 + WNum*2]
            cmd.append(mask_len)  # SendBuff[14 + WNum*2]
            num_bytes = (mask_len + 7) // 8 if mask_len % 8 != 0 else mask_len // 8
            cmd.extend(mask_data[:num_bytes])
            # SendBuff[0] = 16 + WNum * 2 + num_bytes (C# SDK)
            total_len = 16 + w_num * 2 + num_bytes
        else:
            # Normal case: EPC length 0-31
            cmd.extend(epc)       # SendBuff[5...] = EPC data
            cmd.append(mem)       # SendBuff[ENum*2+5]
            cmd.append(word_ptr)  # SendBuff[ENum*2+6]
            cmd.extend(wdt)       # SendBuff[ENum*2+7...] = WNum * 2 bytes
            cmd.extend(password)  # SendBuff[WNum*2 + ENum*2+7...] = 4 bytes
            # SendBuff[0] = ENum * 2 + WNum * 2 + 12 (C# SDK)
            total_len = e_num * 2 + w_num * 2 + 12
        
        # Insert length at the beginning
        cmd.insert(0, total_len)
        
        # Add CRC - C# uses GetCRC(SendBuff, SendBuff[0] - 1)
        crc = self._get_crc(cmd, cmd[0] - 1)
        cmd.extend(crc)
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        
        # Wait for response - C# uses GetDataFromPort(3, 3000)
        result = self._get_data_from_port(3, 3000)
        if result != 0:
            return result
        
        # Parse response
        if self.recv_length >= 4:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                return 49
            
            # Check command response
            if self.recv_buffer[2] == 3:
                status = self.recv_buffer[3]
                if status == 0:
                    error_code = 0
                    return 0
                elif status == 252:
                    error_code = self.recv_buffer[4]
                    return status
                else:
                    return status
            else:
                return 49
        
        return 49
    
    def set_rf_power(self, com_addr: int, power_dbm) -> int:
        """Set RF power - supports both single value and array of values for multiple antennas
        
        Args:
            com_addr: Reader address
            power_dbm: Either bytes (single power for all antennas) or bytes (separate power for each antenna)
                     Both should be bytes to match C# SDK byte types
        """
        if isinstance(power_dbm, (bytes, bytearray)) and len(power_dbm) == 1:
            # Single power value for all antennas
            # Command format: [Length][ComAddr][Command][Data][CRC_Low][CRC_High]
            # Command 47 = SetRfPower
            cmd = bytearray([5, com_addr, 0x2F, power_dbm[0]])  # Length=5, ComAddr, Command=47, Power
        elif isinstance(power_dbm, (bytes, bytearray)) and len(power_dbm) > 1:
            # Multiple power values for different antennas
            # Command format: [Length][ComAddr][Command][PowerArray][CRC_Low][CRC_High]
            cmd = bytearray([4 + len(power_dbm), com_addr, 0x2F])  # Length=4+len, ComAddr, Command=47
            cmd.extend(power_dbm)  # Add power array
        else:
            raise ValueError("power_dbm must be bytes/bytearray (single byte for one antenna, multiple bytes for multiple antennas)")
        
        # Add CRC
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        
        # Wait for response
        result = self._get_data_from_port(47, 1500)
        if result != 0:
            return result
        
        # Parse response
        if self.recv_length >= 4:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                return 49
            
            # Check command response
            if self.recv_buffer[2] == 47:
                return self.recv_buffer[3]  # Return status code
            else:
                return 49
        
        return 49
    
    def set_baud_rate(self, com_addr: bytearray, baud: bytes) -> int:
        """Set baud rate (C# SetBaudRate method)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            baud: Baud rate code as bytes (single byte)
        """
        if len(baud) != 1:
            raise ValueError("baud must be a single byte")
        
        # Command format: [Length][ComAddr][Command][Baud][CRC_Low][CRC_High]
        # Command 40 = SetBaudRate (C# SDK)
        cmd = bytearray([5, com_addr[0], 40, baud[0]])  # Length=5, ComAddr, Command=40, Baud
        
        # Add CRC
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        
        # Wait for response - C# uses GetDataFromPort(40, 1500)
        result = self._get_data_from_port(40, 1500)
        if result != 0:
            return result
        
        # Parse response
        if self.recv_length >= 4:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                return 49
            
            # Check command response
            if self.recv_buffer[2] == 40:
                com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# fComAdr = RecvBuff[1])
                
                # Reconfigure serial port with new baud rate (C# equivalent)
                if self.connection_type == self.CONNECTION_SERIAL and self.serial_port:
                    # Map baud rate codes to actual baud rates (same as C#)
                    baud_map = {
                        0: 9600,
                        1: 19200,
                        2: 38400,
                        5: 57600,
                        6: 115200
                    }
                    new_baud = baud_map.get(baud[0], 57600)  # Default to 57600 like C#
                    
                    try:
                        self.serial_port.close()
                        self.serial_port.baudrate = new_baud
                        self.serial_port.open()
                    except Exception as e:
                        print(f"Warning: Failed to reconfigure serial port: {e}")
                
                return self.recv_buffer[3]  # Return status code
            else:
                return 49
        
        return 49
    
    def set_address(self, com_addr: int, new_addr: int) -> int:
        """Set reader address"""
        # Command format: [Length][ComAddr][Command][NewAddr][CRC_Low][CRC_High]
        # Command 36 = SetAddress (C# SDK)
        cmd = bytearray([5, com_addr, 36, new_addr])  # Length=5, ComAddr, Command=36, NewAddr
        
        # Add CRC
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        
        # Wait for response - C# uses GetDataFromPort(36, 1500)
        result = self._get_data_from_port(36, 1500)
        if result != 0:
            return result
        
        # Parse response
        if self.recv_length >= 4:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                return 49
            
            # Check command response
            if self.recv_buffer[2] == 36:
                return self.recv_buffer[3]  # Return status code
            else:
                return 49
        
        return 49
    
    def set_inventory_scan_time(self, com_addr: bytearray, scan_time: bytes) -> int:
        """Set inventory scan time (C# SetInventoryScanTime method)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            scan_time: Scan time as bytes (single byte)
        """
        if len(scan_time) != 1:
            raise ValueError("scan_time must be a single byte")
        
        cmd = bytearray([5, com_addr[0], 37, scan_time[0]])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(37, 1500)
        if result != 0:
            return result
        if self.recv_length >= 4 and self.recv_buffer[2] == 37:
            com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# fComAdr = RecvBuff[1])
            return self.recv_buffer[3]
        return 49

    def buzzer_and_led_control(self, com_addr: bytearray, active_time: bytes, silent_time: bytes, times: bytes) -> int:
        """Control buzzer and LED (C# command 51)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            active_time: Active time as bytes (single byte)
            silent_time: Silent time as bytes (single byte) 
            times: Number of times as bytes (single byte)
        """
        # Validate single byte parameters
        if len(active_time) != 1 or len(silent_time) != 1 or len(times) != 1:
            raise ValueError("active_time, silent_time, and times must be single bytes")
        
        cmd = bytearray([7, com_addr[0], 51, active_time[0], silent_time[0], times[0]])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(51, 1500)
        if result != 0:
            return result
        if self.recv_length >= 4 and self.recv_buffer[2] == 51:
            com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# fComAdr = RecvBuff[1])
            return self.recv_buffer[3]
        return 49

    def set_antenna_multiplexing(self, com_addr: bytearray, ant: bytes) -> int:
        """Set antenna multiplexing (C# SetAntennaMultiplexing overload 1)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            ant: Antenna value as bytes (single byte)
        """
        if len(ant) != 1:
            raise ValueError("ant must be a single byte")
        
        cmd = bytearray([5, com_addr[0], 63, ant[0]])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(63, 1500)
        if result != 0:
            return result
        if self.recv_length >= 4 and self.recv_buffer[2] == 63:
            com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# fComAdr = RecvBuff[1])
            return self.recv_buffer[3]
        return 49

    def set_ant(self, com_addr: bytearray, set_once: bytes, ant_cfg1: bytes, ant_cfg2: bytes) -> int:
        """Set antenna multiplexing extended (C# SetAntennaMultiplexing overload 2)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            set_once: Set once flag as bytes (single byte)
            ant_cfg1: Antenna configuration 1 as bytes (single byte)
            ant_cfg2: Antenna configuration 2 as bytes (single byte)
        """
        if len(set_once) != 1 or len(ant_cfg1) != 1 or len(ant_cfg2) != 1:
            raise ValueError("set_once, ant_cfg1, and ant_cfg2 must be single bytes")
        
        cmd = bytearray([7, com_addr[0], 63, set_once[0], ant_cfg1[0], ant_cfg2[0]])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(63, 1500)
        if result != 0:
            return result
        if self.recv_length >= 4 and self.recv_buffer[2] == 63:
            com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# fComAdr = RecvBuff[1])
            return self.recv_buffer[3]
        return 49

    def write_epc_g2(self, com_addr: bytearray, password: bytes, write_epc: bytes, enum_val: bytes, error_code: list) -> int:
        """Write EPC to Gen2 tag (C# WriteEPC_G2 method)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            password: Password as bytes (4 bytes)
            write_epc: EPC data to write as bytes (length = enum_val*2)
            enum_val: EPC length as bytes (single byte)
            error_code: Error code as list[0] (will be updated with response value)
        """
        if len(enum_val) != 1:
            raise ValueError("enum_val must be a single byte")
        if len(password) < 4:
            raise ValueError("password must be at least 4 bytes")
        
        # write_epc: bytes of EPC to write, length = enum_val[0]*2
        cmd = bytearray()
        cmd.append(0)  # Placeholder for length
        cmd.append(com_addr[0])
        cmd.append(4)
        cmd.append(enum_val[0])
        cmd.extend(password[:4])
        cmd.extend(write_epc[:enum_val[0]*2])
        cmd[0] = enum_val[0]*2 + 9
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(4, 1500)
        if result != 0:
            return result
        if self.recv_length >= 5 and self.recv_buffer[2] == 4:
            if self.recv_buffer[3] == 0:
                com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# fComAdr = RecvBuff[1])
                error_code[0] = 0
            elif self.recv_buffer[3] == 252:
                error_code[0] = self.recv_buffer[4]
            return self.recv_buffer[3]
        return 49

    def write_rf_power(self, com_addr: int, power_dbm: int) -> int:
        """Write RF power (C# command 121)"""
        cmd = bytearray([5, com_addr, 121, power_dbm])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(121, 1500)
        if result != 0:
            return result
        if self.recv_length >= 4 and self.recv_buffer[2] == 121:
            return self.recv_buffer[3]
        return 49

    def read_rf_power(self, com_addr: int, power_dbm: list) -> int:
        """Read RF power (C# command 122)"""
        cmd = bytearray([4, com_addr, 122])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(122, 1500)
        if result != 0:
            return result
        if self.recv_length >= 5 and self.recv_buffer[2] == 122:
            power_dbm[0] = self.recv_buffer[4]
            return self.recv_buffer[3]
        return 49

    def set_antenna_power(self, com_addr: int, power_dbm: bytes, length: int) -> int:
        """Set antenna power (C# SetAntennaPower method)
        
        Args:
            com_addr: Reader address
            power_dbm: Power values for each antenna
            length: Length of power_dbm array
        """
        # Command format: [Length][ComAddr][Command][PowerArray][CRC_Low][CRC_High]
        # Command 47 = SetAntennaPower
        cmd = bytearray([4 + length, com_addr, 0x2F])  # Length=4+length, ComAddr, Command=47
        cmd.extend(power_dbm[:length])  # Add power array up to specified length
        
        # Add CRC
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        
        # Wait for response
        result = self._get_data_from_port(47, 1500)
        if result != 0:
            return result
        
        # Parse response
        if self.recv_length >= 4:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                return 49
            
            # Check command response
            if self.recv_buffer[2] == 47:
                return self.recv_buffer[3]  # Return status code
            else:
                return 49
        
        return 49

    def get_antenna_power(self, com_addr: int, power_dbm: bytearray, length: list) -> int:
        """Get antenna power (C# command 148)"""
        cmd = bytearray([4, com_addr, 148])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(148, 1500)
        if result != 0:
            return result
        if self.recv_length >= 5 and self.recv_buffer[2] == 148:
            length[0] = self.recv_buffer[0] - 5
            power_dbm[:length[0]] = self.recv_buffer[4:4+length[0]]
            return self.recv_buffer[3]
        return 49

    def set_profile(self, com_addr: bytearray, profile: bytearray) -> int:
        """Set profile (C# command 127)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            profile: Profile value as bytearray[0] (will be updated with response value if status=0)
        """
        # Build command exactly like C#: SendBuff[0] = 5; SendBuff[1] = ComAdr; SendBuff[2] = 127; SendBuff[3] = Profile;
        cmd = bytearray([5, com_addr[0], 127, profile[0]])
        
        # Add CRC exactly like C#: GetCRC(SendBuff, SendBuff[0] - 1)
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        
        # Send command exactly like C#: SendDataToPort(SendBuff, SendBuff[0] + 1)
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            return result  # Return send error immediately (C# returns num if GetDataFromPort fails)
        
        # Get response exactly like C#: num = GetDataFromPort(127, 1500)
        result = self._get_data_from_port(127, 1500)
        if result != 0:
            return result  # Return timeout/communication error (C# returns num)
        
        # Process response exactly like C#: if (num == 0) { if (CheckCRC(RecvBuff, RecvLength) == 0) { ... } }
        if self._check_crc(self.recv_buffer, self.recv_length) != 0:
            return 49  # CRC error (C# returns 49)
        
        # Check command response exactly like C#: if (RecvBuff[2] == 127)
        if self.recv_length >= 6 and self.recv_buffer[2] == 127:  # SDK: Len=0x06, so need at least 6 bytes
            com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# ComAdr = RecvBuff[1])
            
            # According to SDK: Status field should be 0x00 for success
            status = self.recv_buffer[3]
            if status == 0:
                # Success: update profile with Data[] field (SDK: Data[] contains profile)
                if self.recv_length >= 5:
                    profile[0] = self.recv_buffer[4]  # Data[] field contains profile value
                return 0  # SDK: Succeed: 0
            else:
                # Error: return the status code
                return status
        else:
            # Command mismatch or insufficient data
            if self.recv_length >= 4:
                return self.recv_buffer[3]  # Return status code
            return 49  # Default error
        
        return 49  # Fallback (should not reach here)

    def start_read(self, com_addr: bytearray, target: bytes) -> int:
        """Start read (C# StartRead method)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            target: Target as bytes (single byte)
        """
        if len(target) != 1:
            raise ValueError("target must be a single byte")
        
        print(f"[DEBUG] start_read: Starting read with com_addr={com_addr[0]}, target={target[0]}")
        
        cmd = bytearray([5, com_addr[0], 80, target[0]])
        print(f"[DEBUG] start_read: Command before CRC: {cmd.hex()}")
        
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        print(f"[DEBUG] start_read: Full command with CRC: {cmd.hex()}")
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            print(f"[DEBUG] start_read: Send failed with result: {result}")
            return result
        
        print(f"[DEBUG] start_read: Send successful, waiting for response...")
        result = self._get_data_from_port(80, 1500)
        if result != 0:
            print(f"[DEBUG] start_read: Response timeout or error: {result}")
            return result
        
        print(f"[DEBUG] start_read: Response received, length={self.recv_length}, buffer={self.recv_buffer[:self.recv_length].hex()}")
        
        if self.recv_length >= 4 and self.recv_buffer[2] == 80:
            old_com_addr = com_addr[0]
            com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# ComAdr = RecvBuff[1])
            status = self.recv_buffer[3]
            print(f"[DEBUG] start_read: Success - com_addr updated from {old_com_addr} to {com_addr[0]}, status={status}")
            return status
        else:
            print(f"[DEBUG] start_read: Invalid response - length={self.recv_length}, expected_cmd=80, got_cmd={self.recv_buffer[2] if self.recv_length >= 3 else 'N/A'}")
            return 49

    def stop_read(self, com_addr: bytearray) -> int:
        """Stop read (C# StopRead method)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
        """
        cmd = bytearray([4, com_addr[0], 81])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        
        # Use _send_data_noclear to match C# SendDataToPort_Noclear behavior
        result = self._send_data_noclear(cmd, len(cmd))
        if result != 0:
            return result
        result = self._get_data_from_port(81, 1500)
        if result != 0:
            return result
        if self.recv_length >= 4 and self.recv_buffer[2] == 81:
            com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# ComAdr = RecvBuff[1])
            return self.recv_buffer[3]
        return 49

    def select_cmd(self, com_addr: bytearray, antenna: int, session: bytes, sel_action: bytes, 
                   mask_mem: bytes, mask_addr: bytes, mask_len: bytes, mask_data: bytes, truncate: bytes, antenna_num: int = 4) -> int:
        """Select command (C# SelectCmd method) - Gen2 select command for filtering tags
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            antenna: Antenna bitmask (int)
            session: Session as bytes (single byte)
            sel_action: Select action as bytes (single byte)
            mask_mem: Mask memory as bytes (single byte)
            mask_addr: Mask address as bytes (2 bytes)
            mask_len: Mask length as bytes (single byte)
            mask_data: Mask data as bytes
            truncate: Truncate flag as bytes (single byte)
            antenna_num: total number of antennas supported (default 4)
        """
        # Validate single byte parameters
        if len(session) != 1 or len(sel_action) != 1 or len(mask_mem) != 1 or len(mask_len) != 1 or len(truncate) != 1:
            raise ValueError("session, sel_action, mask_mem, mask_len, and truncate must be single bytes")
        if len(mask_addr) < 2:
            raise ValueError("mask_addr must be at least 2 bytes")
        
        mask_bytes = (mask_len[0] + 7) // 8
        
        cmd = bytearray()
        offset = 0
        opcode = 154
        
        # Build frame like C#
        if antenna_num <= 8:
            frame_length = 12 + mask_bytes
            cmd.append(frame_length)  # Length
            cmd.append(com_addr[0])   # ComAddr
            cmd.append(opcode)        # Command
            cmd.append(antenna & 0xFF)  # 1 byte antenna bitmask
        else:
            frame_length = 13 + mask_bytes
            cmd.append(frame_length)  # Length
            cmd.append(com_addr[0])   # ComAddr
            cmd.append(opcode)        # Command
            cmd.append((antenna >> 8) & 0xFF)  # High byte
            cmd.append(antenna & 0xFF)         # Low byte
        
        # Select params
        cmd.append(session[0])
        cmd.append(sel_action[0])
        cmd.append(mask_mem[0])
        cmd.extend(mask_addr[:2])
        cmd.append(mask_len[0])
        if mask_bytes > 0:
            cmd.extend(mask_data[:mask_bytes])
        cmd.append(truncate[0])
        
        print(f"[DEBUG] Select command before CRC: {cmd.hex()}")
        print(f"[DEBUG] Select command length: {cmd[0]}")
        
        # Add CRC
        crc = self._get_crc(cmd, cmd[0] - 1)
        cmd.extend(crc)
        print(f"[DEBUG] Full select command with CRC: {cmd.hex()}")
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            print(f"[DEBUG] Select send failed: {result}")
            return result
        
        result = self._get_data_from_port(opcode, 1500)
        if result != 0:
            print(f"[DEBUG] Select response timeout: {result}")
            return result
        
        print(f"[DEBUG] Select response received: {self.recv_buffer[:self.recv_length].hex()}")
        
        if self.recv_length >= 4:
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                print("[DEBUG] Select response CRC check failed")
                return 49
            if self.recv_buffer[2] == opcode:
                com_addr[0] = self.recv_buffer[1]
                return self.recv_buffer[3]
            else:
                print(f"[DEBUG] Select response command mismatch: expected {opcode}, got {self.recv_buffer[2]}")
                return self.recv_buffer[3]
        return 49

    def set_cfg_parameter(self, com_addr: bytearray, opt: bytes, cfg_num: bytes, data: bytes) -> int:
        """Set configuration parameter (C# SetCfgParameter method)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            opt: Option as bytes (single byte)
            cfg_num: Configuration number as bytes (single byte)
            data: Configuration data as bytes
            
        Returns:
            0 on success, error code on failure
        """
        # Validate single byte parameters
        if len(opt) != 1 or len(cfg_num) != 1:
            raise ValueError("opt and cfg_num must be single bytes")
        
        # Build command exactly like C# SDK
        cmd = bytearray()
        cmd.append(0)  # Placeholder for length
        cmd.append(com_addr[0])  # SendBuff[1]
        cmd.append(234)          # SendBuff[2] = command code 234
        cmd.append(opt[0])       # SendBuff[3]
        cmd.append(cfg_num[0])   # SendBuff[4]
        
        # Add data if provided
        if data:
            cmd.extend(data)     # SendBuff[5...] = data
        
        # Set length: SendBuff[0] = (byte)(6 + len)
        cmd[0] = 6 + len(data)
        
        print(f"[DEBUG] SetCfgParameter command before CRC: {cmd.hex()}")
        print(f"[DEBUG] SetCfgParameter command length: {cmd[0]}")
        
        # Add CRC - C# uses GetCRC(SendBuff, SendBuff[0] - 1)
        crc = self._get_crc(cmd, cmd[0] - 1)
        cmd.extend(crc)
        
        print(f"[DEBUG] Full SetCfgParameter command with CRC: {cmd.hex()}")
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            print(f"[DEBUG] SetCfgParameter send failed: {result}")
            return result
        
        # Wait for response - C# uses GetDataFromPort(234, 1500)
        result = self._get_data_from_port(234, 1500)
        if result != 0:
            print(f"[DEBUG] SetCfgParameter response timeout: {result}")
            return result
        
        print(f"[DEBUG] SetCfgParameter response received: {self.recv_buffer[:self.recv_length].hex()}")
        
        # Parse response exactly like C# SDK
        if self.recv_length >= 4:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                print("[DEBUG] SetCfgParameter response CRC check failed")
                return 49
            
            # Check command response
            if self.recv_buffer[2] == 234:
                com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# ComAdr = RecvBuff[1])
                return self.recv_buffer[3]  # Return status code
            else:
                print(f"[DEBUG] SetCfgParameter response command mismatch: expected 234, got {self.recv_buffer[2]}")
                return self.recv_buffer[3]  # Return status code even if command doesn't match
        
        return 49

    def get_cfg_parameter(self, com_addr: bytearray, cfg_no: bytes, cfg_data: bytearray) -> tuple[int, int]:
        """Get configuration parameter (C# GetCfgParameter method)
        
        Args:
            com_addr: Reader address as bytearray[0] (will be updated with response value)
            cfg_no: Configuration number as bytes (single byte)
            cfg_data: Configuration data buffer as bytearray (will be updated with response data)
            
        Returns:
            Tuple of (status_code, data_length)
        """
        # Validate single byte parameter
        if len(cfg_no) != 1:
            raise ValueError("cfg_no must be a single byte")
        
        # Build command exactly like C# SDK
        cmd = bytearray()
        cmd.append(5)            # SendBuff[0] = 5
        cmd.append(com_addr[0])  # SendBuff[1]
        cmd.append(235)          # SendBuff[2] = command code 235
        cmd.append(cfg_no[0])    # SendBuff[3]
        
        print(f"[DEBUG] GetCfgParameter command before CRC: {cmd.hex()}")
        print(f"[DEBUG] GetCfgParameter command length: {cmd[0]}")
        
        # Add CRC - C# uses GetCRC(SendBuff, SendBuff[0] - 1)
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        
        print(f"[DEBUG] Full GetCfgParameter command with CRC: {cmd.hex()}")
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            print(f"[DEBUG] GetCfgParameter send failed: {result}")
            return result, 0
        
        # Wait for response - C# uses GetDataFromPort(235, 1500)
        result = self._get_data_from_port(235, 1500)
        if result != 0:
            print(f"[DEBUG] GetCfgParameter response timeout: {result}")
            return result, 0
        
        print(f"[DEBUG] GetCfgParameter response received: {self.recv_buffer[:self.recv_length].hex()}")
        
        # Parse response exactly like C# SDK
        if self.recv_length >= 4:
            # Check CRC
            if self._check_crc(self.recv_buffer, self.recv_length) != 0:
                print("[DEBUG] GetCfgParameter response CRC check failed")
                return 49, 0
            
            # Check command response
            if self.recv_buffer[2] == 235:
                com_addr[0] = self.recv_buffer[1]  # Update com_addr with response value (C# ComAdr = RecvBuff[1])
                
                status = self.recv_buffer[3]
                if status == 0:
                    # Success - extract data length and copy data
                    data_len = self.recv_length - 6  # C#: len = RecvLength - 6
                    if data_len > 0:
                        # Copy data to cfg_data buffer
                        cfg_data[:data_len] = self.recv_buffer[4:4+data_len]  # C#: Array.Copy(RecvBuff, 4, cfgData, 0, len)
                        print(f"[DEBUG] GetCfgParameter data extracted: {cfg_data[:data_len].hex()}")
                    
                    return status, data_len
                else:
                    return status, 0
            else:
                print(f"[DEBUG] GetCfgParameter response command mismatch: expected 235, got {self.recv_buffer[2]}")
                return self.recv_buffer[3], 0  # Return status code even if command doesn't match
        
        return 49, 0

    def get_available_data_size(self):
        # Return number of bytes available after offset 0x135
        if len(self.buffer) > 0x135:
            return len(self.buffer) - 0x135
        return 0

    def get_rfid_tag_data(self, output_buffer, output_length_ref):
        import time
        time.sleep(0.005)  # Sleep 5ms

        # Read from the device using the new method
        data = self.read_data_from_port()
        if data:
            size = len(data)
            print(f"[DEBUG] get_rfid_tag_data: Got {size} bytes of data: {data.hex()}")
            output_buffer[:size] = data
            output_length_ref[0] = size
            print(f"[DEBUG] get_rfid_tag_data: Copied {size} bytes to output buffer, length_ref set to {output_length_ref[0]}")
            return 0
        else:
            print(f"[DEBUG] get_rfid_tag_data: No data received, returning 0xFB")
        return 0xFB

    def stop_immediately(self, com_addr: int) -> int:
        """
        Send the StopImmediately command to the device (C# command 147)
        Args:
            com_addr: Communication address
        Returns:
            0 on success
        """
        # Build command: [Length][ComAddr][Command=147][CRC_Low][CRC_High]
        cmd = bytearray([4, com_addr, 147])
        crc = self._get_crc(cmd, len(cmd))
        cmd.extend(crc)
        self._send_data_noclear(cmd, len(cmd))
        return 0 

    def read_data_from_port(self) -> Optional[bytes]:
        """
        Read data from the port (serial or TCP), sleep 5ms, read all available bytes, invoke recv_callback, and return the bytes read.
        Matches the C# ReadDataFromPort logic.
        """
        try:
            if self.connection_type == self.CONNECTION_SERIAL:
                if self.serial_port and self.serial_port.is_open:
                    time.sleep(0.005)  # Sleep 5ms
                    bytes_to_read = self.serial_port.in_waiting
                    print(f"[DEBUG] read_data_from_port: Serial port has {bytes_to_read} bytes waiting")
                    if bytes_to_read > 0:
                        buffer = self.serial_port.read(bytes_to_read)
                        if buffer:
                            print(f"[DEBUG] read_data_from_port: Read {len(buffer)} bytes: {buffer.hex()}")
                            if self.recv_callback:
                                self.recv_callback(self._bytes_to_hex_string(buffer).encode())
                            return buffer
                        else:
                            print(f"[DEBUG] read_data_from_port: No data read despite {bytes_to_read} bytes available")
                    else:
                        print(f"[DEBUG] read_data_from_port: No bytes waiting to read")
                else:
                    print(f"[DEBUG] read_data_from_port: Serial port not open or not available")
            elif self.connection_type == self.CONNECTION_TCP:
                if self.tcp_stream:
                    time.sleep(0.005)
                    try:
                        buffer = self.tcp_stream.recv(1024)
                        print(f"[DEBUG] read_data_from_port: TCP received {len(buffer)} bytes: {buffer.hex()}")
                    except Exception as e:
                        buffer = b''
                        print(f"[DEBUG] read_data_from_port: TCP receive exception: {e}")
                    if buffer:
                        if self.recv_callback:
                            self.recv_callback(self._bytes_to_hex_string(buffer).encode())
                        return buffer
                else:
                    print(f"[DEBUG] read_data_from_port: TCP stream not available")
            else:
                print(f"[DEBUG] read_data_from_port: Unknown connection type: {self.connection_type}")
        except Exception as ex:
            print(f"[DEBUG] read_data_from_port: Exception: {ex}")
        return None 

    def inventory_mix_g2(self, com_addr: bytearray, q_value: bytes, session: bytes,
                        mask_mem: bytes, mask_addr: bytearray, mask_len: bytes,
                        mask_data: bytearray, mask_flag: bytes, read_mem: bytes,
                        read_addr: bytearray, read_len: bytes, psd: bytearray,
                        target: bytes, in_ant: bytes, scan_time: bytes, fast_flag: bytes,
                        epc_list: bytearray, ant: list, total_len: list, card_num: list) -> int:
        """Perform Gen2 inventory mix operation (C# SDK InventoryMix_G2 logic)"""
        # C# SDK defaults scan_time to 20 if 0 is passed
        scan_time_val = scan_time[0] if scan_time[0] != 0 else 20
        print(f"[DEBUG] InventoryMix_G2 parameters: com_addr={com_addr[0]}, q_value={q_value[0]}, session={session[0]}, scan_time={scan_time_val}")
        
        # Build command exactly like C# SDK
        cmd = bytearray()
        cmd.append(com_addr[0])  # SendBuff[1]
        cmd.append(25)           # SendBuff[2] = command code 25 (InventoryMix_G2)
        cmd.append(q_value[0])   # SendBuff[3]
        cmd.append(session[0])   # SendBuff[4]
        
        if mask_flag[0] == 1:
            cmd.append(mask_mem[0])  # SendBuff[5]
            cmd.extend(mask_addr)    # SendBuff[6,7]
            cmd.append(mask_len[0])  # SendBuff[8]
            num_bytes = (mask_len[0] + 7) // 8 if mask_len[0] % 8 != 0 else mask_len[0] // 8
            cmd.extend(mask_data[:num_bytes])
            
            cmd.append(read_mem[0])  # SendBuff[num+9]
            cmd.extend(read_addr)    # SendBuff[num+10, num+11]
            cmd.append(read_len[0])  # SendBuff[num+12]
            cmd.extend(psd)          # SendBuff[num+13...num+16] (4 bytes)
            
            if fast_flag[0] == 1:
                cmd.append(target[0])    # SendBuff[num+17]
                cmd.append(in_ant[0])    # SendBuff[num+18]
                cmd.append(scan_time_val) # SendBuff[num+19]
                # SendBuff[0] = 21 + num
                cmd.insert(0, 21 + num_bytes)
            else:
                # SendBuff[0] = 18 + num
                cmd.insert(0, 18 + num_bytes)
        else:
            cmd.append(read_mem[0])  # SendBuff[5]
            cmd.extend(read_addr)    # SendBuff[6,7]
            cmd.append(read_len[0])  # SendBuff[8]
            cmd.extend(psd)          # SendBuff[9...12] (4 bytes)
            
            if fast_flag[0] == 1:
                cmd.append(target[0])    # SendBuff[13]
                cmd.append(in_ant[0])    # SendBuff[14]
                cmd.append(scan_time_val) # SendBuff[15]
                cmd.insert(0, 17)        # SendBuff[0] = 17
            else:
                cmd.insert(0, 14)        # SendBuff[0] = 14
        
        print(f"[DEBUG] InventoryMix_G2 command before CRC: {cmd.hex()}")
        print(f"[DEBUG] Command length: {cmd[0]}")
        
        # Add CRC - C# uses GetCRC(SendBuff, SendBuff[0] - 1)
        crc = self._get_crc(cmd, cmd[0] - 1)
        cmd.extend(crc)
        
        print(f"[DEBUG] Full InventoryMix_G2 command with CRC: {cmd.hex()}")
        
        result = self._send_data(cmd, len(cmd))
        if result != 0:
            print(f"[DEBUG] InventoryMix_G2 send failed: {result}")
            return result
        
        # C# calls GetInventoryMixG1(Scantime * 100, ...) - scan_time is in 10ms units
        # So scan_time=20 means 2000ms timeout
        return self._get_inventory_mix_g1(scan_time_val * 100, epc_list, ant, total_len, card_num) 

    def _get_inventory_mix_g1(self, scan_time: int, epc_list: bytearray, ant: list, total_len: list, card_num: list) -> int:
        """Get inventory mix data (private method like C# GetInventoryMixG1)"""
        card_num[0] = 0
        total_len[0] = 0
        num = 0
        array = bytearray(4096)  # Buffer for incomplete packets
        num2 = 0  # Remaining bytes from previous read
        start_time = time.time()
        
        try:
            while (time.time() - start_time) * 1000 < scan_time * 2 + 2000:  # Convert to milliseconds
                array2 = self.read_data_from_port()
                if array2 is not None:
                    num = len(array2)
                    if num == 0:
                        continue
                    
                    # Combine previous remaining data with new data
                    array3 = bytearray(num2 + num)
                    array3[:num2] = array[:num2]
                    array3[num2:num2+num] = array2
                    
                    num4 = 0  # Current position in array3
                    while len(array3) - num4 > 5:
                        if array3[num4] >= 5 and array3[num4 + 2] == 25:  # Command 25 = InventoryMix_G2
                            num5 = array3[num4]  # Packet length
                            if len(array3) < num4 + num5 + 1:
                                break
                            
                            # Extract complete packet
                            array4 = array3[num4:num4 + num5 + 1]
                            
                            if self._check_crc(array4, len(array4)) == 0:
                                start_time = time.time()  # Reset timeout timer
                                num6 = array4[0] + 1  # Move to next packet
                                num4 += num6
                                
                                num7 = array4[3]  # Status
                                if num7 in (1, 2, 3, 4):
                                    num8 = array4[5]  # Number of tags
                                    if num8 > 0:
                                        num9 = 6  # Start of tag data
                                        for i in range(num8):
                                            num10 = array4[num9 + 1] & 0x3F  # EPC length
                                            flag = False
                                            phase_begin = 0
                                            phase_end = 0
                                            freqkhz = 0
                                            
                                            if (array4[num9 + 1] & 0x40) > 0:
                                                flag = True
                                            
                                            if not flag:
                                                # EPC only (3 bytes: packet param + EPC length + EPC data)
                                                epc_list[total_len[0]:total_len[0] + num10 + 3] = array4[num9:num9 + num10 + 3]
                                                total_len[0] += num10 + 3
                                            else:
                                                # EPC + extra data (7 bytes: packet param + EPC length + EPC data + extra data)
                                                epc_list[total_len[0]:total_len[0] + num10 + 7] = array4[num9:num9 + num10 + 7]
                                                total_len[0] += num10 + 7
                                                
                                                # Extract phase and frequency data
                                                if num9 + num10 + 9 < len(array4):
                                                    phase_begin = array4[num9 + num10 + 3] * 256 + array4[num9 + num10 + 4]
                                                    phase_end = array4[num9 + num10 + 5] * 256 + array4[num9 + num10 + 6]
                                                    freqkhz = (array4[num9 + num10 + 7] << 16) + (array4[num9 + num10 + 8] << 8) + array4[num9 + num10 + 9]
                                            
                                            card_num[0] += 1
                                            ant[0] = array4[4]  # Antenna number
                                            
                                            # Call callback if available (equivalent to C# ReceiveCallback)
                                            if hasattr(self, 'receive_callback') and self.receive_callback is not None:
                                                # Create RFIDTag object with all the data
                                                from rfid_tag import RFIDTag
                                                tag = RFIDTag()
                                                tag.device_name = getattr(self, 'dev_name', 'Unknown')
                                                tag.antenna = array4[4]
                                                tag.len = array4[num9 + 1]
                                                tag.packet_param = array4[num9]
                                                tag.phase_begin = phase_begin
                                                tag.phase_end = phase_end
                                                tag.rssi = array4[num9 + 2 + num10] if num9 + 2 + num10 < len(array4) else 0
                                                tag.freqkhz = freqkhz
                                                
                                                # Extract EPC data
                                                epc_data = array4[num9 + 2:num9 + 2 + num10]
                                                tag.epc = self._bytes_to_hex_string(epc_data)
                                                
                                                # Call the callback
                                                self.receive_callback(tag)
                                            
                                            # Move to next tag
                                            if flag:
                                                num9 += 10 + num10  # EPC + extra data
                                            else:
                                                num9 += 3 + num10   # EPC only
                                
                                if num7 != 3:  # Not continuing
                                    return num7
                            else:
                                num4 += 1  # CRC check failed, move to next byte
                        else:
                            num4 += 1  # Not a valid packet, move to next byte
                    
                    # Save remaining incomplete data for next iteration
                    if len(array3) > num4:
                        num2 = len(array3) - num4
                        array[:num2] = array3[num4:num4 + num2]
                    else:
                        num2 = 0
                else:
                    time.sleep(0.005)  # 5ms sleep like C# Thread.Sleep(5)
        
        except Exception as ex:
            print(f"[DEBUG] Exception in GetInventoryMixG1: {ex}")
        
        return 48  # Timeout 