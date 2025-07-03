"""
Main UHF Reader class providing high-level interface for UHF RFID operations
"""

import threading
import time
import serial.tools.list_ports
from typing import Optional, Callable, List, Dict, Any
from reader import Reader
from rfid_tag import RFIDTag
from exceptions import (
    UHFReaderError, ConnectionError, TimeoutError,
    ReaderNotConnectedError, OperationInProgressError
)

class UHFReader:
    """
    High-level UHF RFID Reader class that provides easy-to-use interface
    for RFID operations including connection management, inventory,
    read/write operations, and configuration.
    """
    
    def __init__(self):
        """Initialize the UHF reader"""
        self.uhf = Reader()
        self.is_connected = False
        self.is_scanning = False
        self.callback: Optional[Callable[[RFIDTag], None]] = None
        self.to_stop_thread = False
        self.scan_thread: Optional[threading.Thread] = None
        self.com_addr = 255
    
    def init_rfid_callback(self, callback: Callable[[RFIDTag], None]) -> None:
        """
        Initialize RFID callback function
        
        Args:
            callback: Function to call when RFID tags are detected
        """
        self.callback = callback
        self.uhf.receive_callback = callback
    
    def open_net_port(self, port: int, ip_addr: str, com_addr: int) -> int:
        """
        Open network connection to the reader
        
        Args:
            port: TCP port number
            ip_addr: IP address of the reader
            com_addr: Communication address (will be updated with actual address)
            
        Returns:
            0 on success, error code on failure
        """
        if self.is_connected:
            return 53  # Already connected
        
        result = self.uhf.open_by_tcp(ip_addr, port, com_addr)
        if result == 0:
            self.is_scanning = False
            self.is_connected = True
            self.com_addr = com_addr
        
        return result
    
    def close_net_port(self) -> int:
        """
        Close network connection
        
        Returns:
            0 on success, error code on failure
        """
        if self.is_scanning:
            return 51  # Scanning in progress
        
        if not self.is_connected:
            return 0
        
        result = self.uhf.close_by_tcp()
        if result == 0:
            self.is_connected = False
            self.is_scanning = False
        
        return result
    
    def open_com_port(self, port, com_addr: int, baud: int, skip_verification: bool = False) -> int:
        """
        Open serial connection to the reader
        
        Args:
            port: COM port number or device path
            com_addr: Communication address (will be updated with actual address)
            baud: Baud rate code (0=9600, 1=19200, 2=38400, 5=57600, 6=115200)
            skip_verification: Skip reader verification (for testing with non-RFID devices)
            
        Returns:
            0 on success, error code on failure
        """
        if self.is_connected:
            return 53  # Already connected
        
        result = self.uhf.open_by_com(port, com_addr, baud, skip_verification)
        if result == 0:
            self.is_scanning = False
            self.is_connected = True
            self.com_addr = com_addr
        
        return result
    
    def close_com_port(self) -> int:
        """
        Close serial connection
        
        Returns:
            0 on success, error code on failure
        """
        if self.is_scanning:
            return 51  # Scanning in progress
        
        if not self.is_connected:
            return 0
        
        result = self.uhf.close_by_com()
        if result == 0:
            self.is_connected = False
            self.is_scanning = False
        
        return result
    
    def auto_open_com_port(self, com_addr: int, baud: int) -> tuple[int, int]:
        """
        Automatically find and open COM port
        
        Args:
            com_addr: Communication address (will be updated with actual address)
            baud: Baud rate code
            
        Returns:
            Tuple of (port_number, result_code)
        """
        available_ports = [port.device for port in serial.tools.list_ports.comports()]
        
        if not available_ports:
            return 0, 48  # No ports available
        
        for port_name in available_ports:
            try:
                # Extract port number from COM port name
                if port_name.startswith('COM'):
                    port_num = int(port_name[3:])
                    result = self.uhf.open_by_com(port_num, com_addr, baud)
                    if result == 0:
                        self.is_scanning = False
                        self.is_connected = True
                        self.com_addr = com_addr
                        return port_num, result
            except (ValueError, IndexError):
                continue
        
        return 0, 48  # No working port found
    
    def get_reader_information(self) -> Dict[str, Any]:
        """
        Get reader information
        
        Returns:
            Dictionary containing reader information
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
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
        
        result = self.uhf.get_reader_information(
            self.com_addr, version_info, reader_type, tr_type,
            dmax_fre, dmin_fre, power_dbm, scan_time,
            ant, beep_en, output_rep, check_ant
        )
        
        if result == 0:
            return {
                'com_addr': self.com_addr,
                'version_info': bytes(version_info).hex().upper(),
                'reader_type': reader_type[0],
                'tr_type': tr_type[0],
                'dmax_fre': dmax_fre[0],
                'dmin_fre': dmin_fre[0],
                'power_dbm': power_dbm[0],
                'scan_time': scan_time[0],
                'ant': ant[0],
                'beep_en': beep_en[0],
                'output_rep': output_rep[0],
                'check_ant': check_ant[0]
            }
        else:
            raise UHFReaderError(f"Failed to get reader information: {result}")
    
    def set_region(self, dmax_fre: int, dmin_fre: int) -> int:
        """
        Set frequency region
        
        Args:
            dmax_fre: Maximum frequency
            dmin_fre: Minimum frequency
            
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        return self.uhf.set_region(self.com_addr, dmax_fre, dmin_fre)
    
    def set_address(self, new_addr: int) -> int:
        """
        Set reader address
        
        Args:
            new_addr: New address
            
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        result = self.uhf.set_address(self.com_addr, new_addr)
        if result == 0:
            self.com_addr = new_addr
        
        return result
    
    def set_inventory_scan_time(self, scan_time: int) -> int:
        """
        Set inventory scan time
        
        Args:
            scan_time: Scan time in seconds
            
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        com_addr = bytearray([self.com_addr])
        scan_time_bytes = bytes([scan_time])
        return self.uhf.set_inventory_scan_time(com_addr, scan_time_bytes)
    
    def set_baud_rate(self, baud: int) -> int:
        """
        Set baud rate
        
        Args:
            baud: Baud rate code (0=9600, 1=19200, 2=38400, 5=57600, 6=115200)
            
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        com_addr = bytearray([self.com_addr])
        baud_bytes = bytes([baud])
        return self.uhf.set_baud_rate(com_addr, baud_bytes)
    
    def set_rf_power(self, power_dbm: int) -> int:
        """
        Set RF power
        
        Args:
            power_dbm: Power in dBm
            
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        # Convert decimal power to bytes for SDK
        power_bytes = bytes([power_dbm])
        return self.uhf.set_rf_power(self.com_addr, power_bytes)
    
    def inventory_g2(self, q_value: int = 4, session: int = 0, 
                    scan_time: int = 5, target: int = 0, 
                    in_ant: int = 0) -> List[RFIDTag]:
        """
        Perform Gen2 inventory operation
        
        Args:
            q_value: Q value for inventory (0-15)
            session: Session flag (0-3)
            scan_time: Scan time in 10-millisecond units (e.g., 20 = 200ms, 100 = 1s)
            target: Target flag (0-1)
            in_ant: Input antenna (0-255)
            
        Returns:
            List of RFIDTag objects found
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        # Prepare parameters - convert int to bytes/bytearray for low-level API
        com_addr = bytearray([self.com_addr])
        q_value_bytes = bytes([q_value])
        session_bytes = bytes([session])
        mask_mem_bytes = bytes([0])
        mask_addr = bytearray(2)
        mask_len_bytes = bytes([0])
        mask_data = bytearray()
        mask_flag_bytes = bytes([0])
        addr_tid_bytes = bytes([0])
        len_tid_bytes = bytes([0])
        tid_flag_bytes = bytes([0])
        target_bytes = bytes([target])
        in_ant_bytes = bytes([in_ant])
        scan_time_bytes = bytes([scan_time])
        fast_flag_bytes = bytes([0])
        epc_list = bytearray(8192)
        ant = [0]
        total_len = [0]
        card_num = [0]
        rssi_list = []  # Collect RSSI values
        
        result = self.uhf.inventory_g2(
            com_addr, q_value_bytes, session_bytes, mask_mem_bytes, mask_addr,
            mask_len_bytes, mask_data, mask_flag_bytes, addr_tid_bytes, len_tid_bytes,
            tid_flag_bytes, target_bytes, in_ant_bytes, scan_time_bytes, fast_flag_bytes,
            epc_list, ant, total_len, card_num, rssi_list
        )
        
        # In C# SDK, status codes 1, 2, 3, 4 are all valid success codes for inventory
        if result in (0, 1, 2, 3, 4):
            # Parse EPC list and create RFIDTag objects
            tags = []
            offset = 0
            for i in range(card_num[0]):
                if offset + 1 <= total_len[0]:
                    epc_len = epc_list[offset] & 0x3F
                    has_extra = (epc_list[offset] & 0x40) > 0
                    offset += 1
                    if offset + epc_len <= total_len[0]:
                        epc_data = epc_list[offset:offset + epc_len]
                        offset += epc_len
                        if offset < total_len[0]:
                            rssi = epc_list[offset]
                            offset += 1
                        else:
                            rssi = 0
                        if has_extra:
                            extra_len = 7
                            offset += extra_len  # skip extra fields
                        tag = RFIDTag(
                            uid=epc_data.hex().upper(),
                            ant=ant[0],
                            rssi=rssi,
                            device_name=self.uhf.device_name
                        )
                        tags.append(tag)
            return tags
        else:
            raise UHFReaderError(f"Inventory failed: {result}")
    
    def read_data_g2(self, epc: str, mem: int = 3, word_ptr: int = 0, 
                    num: int = 1, password: str = "00000000") -> bytes:
        """
        Read data from Gen2 tag
        
        Args:
            epc: EPC of the tag
            mem: Memory bank (0=Reserved, 1=EPC, 2=TID, 3=User)
            word_ptr: Word pointer
            num: Number of words to read
            password: Access password
            
        Returns:
            Read data as bytes
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        # Convert parameters
        epc_bytes = bytes.fromhex(epc)
        e_num = len(epc_bytes)
        password_bytes = bytes.fromhex(password)
        mask_mem = 0
        mask_addr = bytes(2)
        mask_len = 0
        mask_data = bytes()
        data = bytearray(256)
        error_code = [0]
        
        result = self.uhf.read_data_g2(
            self.com_addr, epc_bytes, e_num, mem, word_ptr, num,
            password_bytes, mask_mem, mask_addr, mask_len, mask_data,
            data, error_code
        )
        
        if result == 0:
            return bytes(data)
        else:
            raise UHFReaderError(f"Read data failed: {result}")
    
    def write_data_g2(self, epc: str, data: bytes, mem: int = 3, 
                     word_ptr: int = 0, password: str = "00000000") -> int:
        """
        Write data to Gen2 tag
        
        Args:
            epc: EPC of the tag
            data: Data to write
            mem: Memory bank (0=Reserved, 1=EPC, 2=TID, 3=User)
            word_ptr: Word pointer
            password: Access password
            
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        # Convert parameters
        epc_bytes = bytes.fromhex(epc)
        e_num = len(epc_bytes)
        w_num = len(data)
        password_bytes = bytes.fromhex(password)
        mask_mem = 0
        mask_addr = bytes(2)
        mask_len = 0
        mask_data = bytes()
        error_code = 0
        
        return self.uhf.write_data_g2(
            self.com_addr, epc_bytes, w_num, e_num, mem, word_ptr,
            data, password_bytes, mask_mem, mask_addr, mask_len,
            mask_data, error_code
        )
    
    def start_inventory(self, target: int = 0) -> int:
        """
        Start continuous inventory
        
        Args:
            target: Target flag
            
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        if self.is_scanning:
            return 51  # Already scanning
        
        if not self.callback:
            raise UHFReaderError("No callback function set")
        
        self.is_scanning = True
        self.to_stop_thread = False
        
        # Start scanning thread
        self.scan_thread = threading.Thread(target=self._work_process)
        self.scan_thread.daemon = True
        self.scan_thread.start()
        
        return 0
    
    def stop_inventory(self) -> int:
        """
        Stop continuous inventory
        
        Returns:
            0 on success, error code on failure
        """
        if not self.is_scanning:
            return 0
        
        self.to_stop_thread = True
        self.is_scanning = False
        
        # Wait for thread to finish
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=2.0)
        
        return 0
    
    def _work_process(self) -> None:
        """Background thread for continuous inventory"""
        while not self.to_stop_thread and self.is_scanning:
            try:
                # Perform single inventory
                tags = self.inventory_g2(scan_time=1)
                
                # Call callback for each tag
                if self.callback and tags:
                    for tag in tags:
                        self.callback(tag)
                
                time.sleep(0.1)  # Small delay
                
            except Exception as e:
                print(f"Error in work process: {e}")
                time.sleep(1.0)  # Longer delay on error
    
    def hex_string_to_bytes(self, hex_str: str) -> bytes:
        """
        Convert hex string to bytes
        
        Args:
            hex_str: Hex string
            
        Returns:
            Bytes object
        """
        return bytes.fromhex(hex_str.replace(" ", ""))
    
    def bytes_to_hex_string(self, data: bytes) -> str:
        """
        Convert bytes to hex string
        
        Args:
            data: Bytes object
            
        Returns:
            Hex string
        """
        return data.hex().upper()
    
    def check_crc(self, hex_str: str) -> bool:
        """
        Check CRC of hex string
        
        Args:
            hex_str: Hex string with CRC
            
        Returns:
            True if CRC is valid, False otherwise
        """
        try:
            data = bytes.fromhex(hex_str.replace(" ", ""))
            if len(data) < 2:
                return False
            
            # Extract data without CRC
            data_without_crc = data[:-2]
            
            # Calculate expected CRC
            expected_crc = self.uhf._get_crc(data_without_crc, len(data_without_crc))
            
            # Compare with received CRC
            received_crc = data[-2:]
            
            return expected_crc == received_crc
            
        except Exception:
            return False
    
    def get_available_ports(self) -> List[str]:
        """
        Get list of available COM ports
        
        Returns:
            List of available port names
        """
        return [port.device for port in serial.tools.list_ports.comports()]
    
    def is_port_available(self, port_name: str) -> bool:
        """
        Check if a specific port is available
        
        Args:
            port_name: Port name (e.g., "COM1")
            
        Returns:
            True if port is available, False otherwise
        """
        available_ports = self.get_available_ports()
        return port_name in available_ports

    def buzzer_and_led_control(self, active_time: int, silent_time: int, times: int) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        com_addr = bytearray([self.com_addr])
        active_time_bytes = bytes([active_time])
        silent_time_bytes = bytes([silent_time])
        times_bytes = bytes([times])
        return self.uhf.buzzer_and_led_control(com_addr, active_time_bytes, silent_time_bytes, times_bytes)

    def set_antenna_multiplexing(self, ant: int) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        com_addr = bytearray([self.com_addr])
        ant_bytes = bytes([ant])
        return self.uhf.set_antenna_multiplexing(com_addr, ant_bytes)

    def set_inventory_interval(self, read_pause_time: int) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        return self.uhf.set_inventory_interval(self.com_addr, read_pause_time)

    def write_epc_g2(self, password: str, write_epc: str) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        com_addr = bytearray([self.com_addr])
        password_bytes = bytes.fromhex(password)
        write_epc_bytes = bytes.fromhex(write_epc)
        enum_val_bytes = bytes([len(write_epc_bytes) // 2])
        error_code = [0]
        result = self.uhf.write_epc_g2(com_addr, password_bytes, write_epc_bytes, enum_val_bytes, error_code)
        if result == 0:
            return 0
        else:
            raise UHFReaderError(f"Write EPC failed: {result}, error_code: {error_code[0]}")

    def write_rf_power(self, power_dbm: int) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        # Convert decimal power to bytes for SDK
        power_bytes = bytes([power_dbm])
        return self.uhf.write_rf_power(self.com_addr, power_bytes)

    def read_rf_power(self) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        power_dbm = [0]
        result = self.uhf.read_rf_power(self.com_addr, power_dbm)
        if result == 0:
            return power_dbm[0]
        else:
            raise UHFReaderError(f"Read RF power failed: {result}")

    def set_antenna_power(self, power_dbm: bytes) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        return self.uhf.set_antenna_power(self.com_addr, power_dbm)

    def get_antenna_power(self) -> bytes:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        power_dbm = bytearray(8)
        length = [0]
        result = self.uhf.get_antenna_power(self.com_addr, power_dbm, length)
        if result == 0:
            return bytes(power_dbm[:length[0]])
        else:
            raise UHFReaderError(f"Get antenna power failed: {result}")

    def set_profile(self, profile: int) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        profile_bytearray = bytearray([profile])
        result = self.uhf.set_profile(self.com_addr, profile_bytearray)
        if result == 0:
            return profile_bytearray[0]
        else:
            raise UHFReaderError(f"Set profile failed: {result}")

    def start_read(self, target: int = 0) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        com_addr = bytearray([self.com_addr])
        target_bytes = bytes([target])
        return self.uhf.start_read(com_addr, target_bytes)

    def stop_read(self) -> int:
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        com_addr = bytearray([self.com_addr])
        return self.uhf.stop_read(com_addr)

    def select_cmd(self, antenna: int, session: int, sel_action: int, mask_mem: int, 
                   mask_addr: bytes, mask_len: int, mask_data: bytes, truncate: int, antenna_num: int = 4) -> int:
        """
        Select command (Gen2 select command for filtering tags)
        Args:
            antenna: Antenna number (bitmask or value)
            session: Session (0-3)
            sel_action: Select action (0-7)
            mask_mem: Mask memory bank (0-3)
            mask_addr: Mask address (2 bytes)
            mask_len: Mask length in bits
            mask_data: Mask data bytes
            truncate: Truncate flag (0-1)
            antenna_num: total number of antennas supported (default 4)
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        # Convert parameters to bytes/bytearray for low-level API
        com_addr = bytearray([self.com_addr])
        session_bytes = bytes([session])
        sel_action_bytes = bytes([sel_action])
        mask_mem_bytes = bytes([mask_mem])
        mask_len_bytes = bytes([mask_len])
        truncate_bytes = bytes([truncate])
        
        result = self.uhf.select_cmd(
            com_addr, antenna, session_bytes, sel_action_bytes, 
            mask_mem_bytes, mask_addr, mask_len_bytes, mask_data, truncate_bytes, antenna_num
        )
        
        # Update com_addr if successful
        if result == 0:
            self.com_addr = com_addr[0]
        
        return result

    def set_cfg_parameter(self, opt: int, cfg_num: int, data: bytes) -> int:
        """
        Set configuration parameter
        
        Args:
            opt: Option (single byte)
            cfg_num: Configuration number (single byte)
            data: Configuration data as bytes
            
        Returns:
            0 on success, error code on failure
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        # Convert parameters to bytes/bytearray for low-level API
        com_addr = bytearray([self.com_addr])
        opt_bytes = bytes([opt])
        cfg_num_bytes = bytes([cfg_num])
        
        result = self.uhf.set_cfg_parameter(com_addr, opt_bytes, cfg_num_bytes, data)
        
        # Update com_addr if successful
        if result == 0:
            self.com_addr = com_addr[0]
        
        return result

    def get_cfg_parameter(self, cfg_no: int, cfg_data: bytearray, data_len: list) -> int:
        """
        Get configuration parameter
        
        Args:
            cfg_no: Configuration number (single byte)
            cfg_data: Configuration data buffer as bytearray (will be updated with response data)
            data_len: Data length as list[0] (will be updated with actual data length)
            
        Returns:
            Status code (0 on success, error code on failure)
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        # Convert parameters to bytes/bytearray for low-level API
        com_addr = bytearray([self.com_addr])
        cfg_no_bytes = bytes([cfg_no])
        
        status, actual_len = self.uhf.get_cfg_parameter(com_addr, cfg_no_bytes, cfg_data)
        
        # Update com_addr and data_len if successful
        if status == 0:
            self.com_addr = com_addr[0]
            data_len[0] = actual_len
        
        return status 