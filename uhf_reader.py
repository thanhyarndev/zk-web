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
import logging
logger = logging.getLogger(__name__)

class UHFReader:
    """
    High-level UHF RFID Reader class that provides easy-to-use interface
    for RFID operations including connection management, inventory,
    read/write operations, and configuration.
    """
    
    #CHECK
    def __init__(self):
        """Initialize the UHF reader"""
        self.uhf = Reader()
        self.is_connected = False
        self.is_scanning = False
        self.callback: Optional[Callable[[RFIDTag], None]] = None
        self.to_stop_thread = False
        self.scan_thread: Optional[threading.Thread] = None
        self.com_addr = 255
    
    #CHECK
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
    
    #CHECK
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
    
    #CHECK
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
    
    #CHECK
    def get_reader_information(self, com_addr: int, version_info: bytearray, reader_type: list, tr_type: list, 
                             dmax_fre: list, dmin_fre: list, power_dbm: list, scan_time: list,
                             ant_cfg0: list, beep_en: list, output_rep: list, check_ant: list) -> int:
        """
        Get reader information - strict C# equivalent
        
        Args:
            com_addr: Reader address (can be modified)
            version_info: Version info array (2 bytes)
            reader_type: Reader type (output)
            tr_type: Transmitter type (output)
            dmax_fre: Max frequency (output)
            dmin_fre: Min frequency (output)
            power_dbm: Power in dBm (output)
            scan_time: Scan time (output)
            ant_cfg0: Antenna configuration byte 0 (output)
            beep_en: Beep enable (output)
            output_rep: Output report (output)
            check_ant: Check antenna (output)
            
        Returns:
            0 on success, error code on failure
        """
        return self.uhf.get_reader_information(com_addr, version_info, reader_type, tr_type,
                                             dmax_fre, dmin_fre, power_dbm, scan_time,
                                             ant_cfg0, beep_en, output_rep, check_ant)
    
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
                    in_ant: int = 0, tid_flag: int = 0, fast_flag: int = 0,
                    tid_addr: int = 0, tid_len: int = 0) -> List[RFIDTag]:
        """
        Perform Gen2 inventory operation
        
        Args:
            q_value: Q value for inventory (0-15)
            session: Session flag (0-3)
            scan_time: Scan time in 10-millisecond units (e.g., 20 = 200ms, 100 = 1s)
            target: Target flag (0-1)
            in_ant: Input antenna (0-255)
            tid_flag: TID flag (0=EPC mode, 1=TID mode)
            tid_addr: TID start address (when tid_flag=1)
            tid_len: TID length (when tid_flag=1)
            
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
        addr_tid_bytes = bytes([tid_addr])  # Use TID address parameter
        len_tid_bytes = bytes([tid_len])    # Use TID length parameter
        tid_flag_bytes = bytes([tid_flag])  # Use TID flag parameter
        target_bytes = bytes([target])
        in_ant_bytes = bytes([in_ant])
        scan_time_bytes = bytes([scan_time])
        fast_flag_bytes = bytes([fast_flag])
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
                            epc=epc_data.hex().upper(),
                            antenna=ant[0],
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
    
    #CHECK
    def start_inventory(self, target: int = 0) -> int:
        """
        Start continuous inventory (C# logic: gọi StartRead trước, nếu thành công mới tạo thread đọc)
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

        # Gọi start_read trước (giống C# StartRead)

        result = self.uhf.start_read(bytearray([self.com_addr]), bytes([target]))
        if result != 0:
            return 0

        self.is_scanning = True
        self.to_stop_thread = False

        # Start scanning thread
        self.scan_thread = threading.Thread(target=self._work_process)
        self.scan_thread.daemon = True
        self.scan_thread.start()

        return 0
    
    #CHECK
    def stop_immediately(self, com_addr: int = None) -> int:
        """
        Call stop_immediately on the underlying Reader (C# StopImmediately)
        Args:
            com_addr: Communication address (default: self.com_addr)
        Returns:
            0 on success
        """
        if com_addr is None:
            com_addr = self.com_addr
        return self.uhf.stop_immediately(com_addr)

    #CHECK
    def stop_inventory(self) -> int:
        """
        Stop continuous inventory (C# logic: set stop flag, call stop_immediately, wait for thread, then stop_read)
        Returns:
            0 on success, error code on failure
        """
        if not self.is_scanning:
            return 0

        self.to_stop_thread = True
        self.is_scanning = False

        # Call stop_immediately before waiting for thread (C# logic)
        self.stop_immediately(self.com_addr)

        # Wait for thread to finish
        if self.scan_thread and self.scan_thread.is_alive():
            while self.scan_thread.is_alive():
                time.sleep(0.001)  # Sleep 1ms like C#
        self.scan_thread = None

        time.sleep(0.05)  # Add 50ms delay to let device become idle

        # Now send stop command to device
        try:
            if not self.is_connected:
                raise ReaderNotConnectedError("Reader is not connected")
            com_addr = bytearray([self.com_addr])
            result = self.uhf.stop_read(com_addr)
        except Exception as e:
            print(f"Error in stop_read: {e}")
            result = -1

        return result
    
    #CHECK
    def _work_process(self) -> None:
        """Background thread for continuous inventory, giống logic C# workProcess"""
        import time
        print("[DEBUG] _work_process started. self.callback is set:", self.callback is not None)
        fInventory_EPC_List = ""
        start_time = int(time.time() * 1000)
        while not self.to_stop_thread and self.is_scanning:
            try:
                rfid_data = bytearray(4096)
                valid_data_length = [0]
                fCmdRet = self.uhf.get_rfid_tag_data(rfid_data, valid_data_length)
                print(f"[DEBUG] fCmdRet: {fCmdRet}, valid_data_length: {valid_data_length[0]}")
                if valid_data_length[0] > 0:
                    print(f"[DEBUG] rfid_data (len={valid_data_length[0]}): {rfid_data[:valid_data_length[0]].hex()}")
                if fCmdRet == 0:
                    start_time = int(time.time() * 1000)
                    try:
                        daw = rfid_data[:valid_data_length[0]]
                        temp = daw.hex().upper()
                        print(f"[DEBUG] daw(hex): {temp}")
                        fInventory_EPC_List += temp
                        while len(fInventory_EPC_List) > 18:
                            FlagStr = "EE00"
                            nindex = fInventory_EPC_List.find(FlagStr)
                            print(f"[DEBUG] Frame search: nindex={nindex}, fInventory_EPC_List={fInventory_EPC_List}")
                            if nindex > 3:
                                fInventory_EPC_List = fInventory_EPC_List[nindex - 4:]
                            else:
                                fInventory_EPC_List = fInventory_EPC_List[2:]
                                continue
                            NumLen = int(fInventory_EPC_List[:2], 16) * 2 + 2
                            print(f"[DEBUG] NumLen: {NumLen}, fInventory_EPC_List length: {len(fInventory_EPC_List)}")
                            if len(fInventory_EPC_List) < NumLen:
                                print("[DEBUG] Not enough data for full frame, breaking.")
                                break
                            temp1 = fInventory_EPC_List[:NumLen]
                            fInventory_EPC_List = fInventory_EPC_List[NumLen:]
                            print(f"[DEBUG] temp1 (frame): {temp1}")
                            if not self.check_crc(temp1):
                                print("[DEBUG] CRC check failed for frame.")
                                continue
                            AntStr = temp1[8:10]
                            lenstr = str(int(temp1[10:12], 16))
                            length = int(lenstr)
                            m_phase = False
                            phase_begin = 0
                            phase_end = 0
                            freqkhz = 0
                            if (length & 0x40) > 0:
                                m_phase = True
                            epc_len = (length & 0x3F) * 2
                            EPCStr = temp1[12:12 + epc_len]
                            RSSI = temp1[12 + epc_len:12 + epc_len + 2]
                            if m_phase:
                                temp_phase = temp1[-18:-4]
                                phase_begin = int(temp_phase[:4], 16)
                                phase_end = int(temp_phase[4:8], 16)
                                freqkhz = int(temp_phase[8:14], 16)
                            if self.callback:
                                tag = RFIDTag(
                                    epc=EPCStr,
                                    antenna=int(AntStr, 16),
                                    rssi=int(RSSI, 16) if RSSI else 0,
                                    device_name=getattr(self.uhf, 'device_name', None)
                                )
                                tag.phase_begin = phase_begin
                                tag.phase_end = phase_end
                                tag.freqkhz = freqkhz
                                print(f"[DEBUG] Calling callback for tag: {tag.__dict__ if hasattr(tag, '__dict__') else tag}")
                                self.callback(tag)
                    except Exception as ex:
                        print(f"Exception in work_process parse: {ex}")
                else:
                    now = int(time.time() * 1000)
                    if now - start_time > 10000:
                        print("[DEBUG] 10s timeout reached, resetting start_time.")
                        start_time = now

                        version_info = bytearray(2)
                        reader_type = [0]
                        tr_type = [0]
                        dmax_fre = [0]
                        dmin_fre = [0]
                        power_dbm = [0]
                        scan_time = [0]
                        ant_cfg0 = [0]
                        beep_en = [0]
                        output_rep = [0]
                        check_ant = [0]
                        fCmdRet = self.uhf.get_reader_information(self.com_addr, version_info, reader_type, tr_type,
                                             dmax_fre, dmin_fre, power_dbm, scan_time,
                                             ant_cfg0, beep_en, output_rep, check_ant)
                time.sleep(0.05)
            except Exception as e:
                print(f"Error in work process: {e}")
                time.sleep(1.0)
    
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
            raise UHFReaderError(f"Write EPC failed: {result}")

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

    def set_profile(self, com_addr: int = None, profile: int = None):
        """
        Set profile - exact C# SetProfile(ref byte fComAdr, ref byte Profile) implementation
        
        Args:
            com_addr: Reader address (will be converted to byte)
            profile: Profile value (will be converted to byte)
        Returns:
            (result_code, new_profile)
            result_code: 0 on success, error code on failure
            new_profile: updated profile value (only valid if result_code == 0)
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        # Use instance com_addr if not provided
        if com_addr is None:
            com_addr = self.com_addr
        
        # Use default profile if not provided
        if profile is None:
            profile = 1  # Default profile
        
        # Convert to bytes (C# byte type) - ensure values are in valid byte range (0-255)
        com_addr_byte = com_addr & 0xFF
        profile_byte = profile & 0xFF
        
        # Create bytearrays for C# ref parameter simulation
        com_addr_bytearray = bytearray([com_addr_byte])
        profile_bytearray = bytearray([profile_byte])
        
        # Call low-level function (exact C# SetProfile behavior)
        result = self.uhf.set_profile(com_addr_bytearray, profile_bytearray)
        
        # Update instance variables with response values (C# ref parameter behavior)
        if result == 0:
            self.com_addr = com_addr_bytearray[0]
            return 0, profile_bytearray[0]
        else:
            return result, None

    #CHECK
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

    #CHECK
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

    #CHECK
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

    def hex_string_to_byte_array(self, hex_string: str) -> bytes:
        """
        Convert hex string to byte array - equivalent to C# HexStringToByteArray
        """
        try:
            # Remove any spaces and ensure even length
            hex_string = hex_string.replace(" ", "").upper()
            if len(hex_string) % 2 != 0:
                hex_string = "0" + hex_string
            
            # Convert to bytes
            return bytes.fromhex(hex_string)
        except Exception as e:
            logger.error(f"Error converting hex string to byte array: {e}")
            raise UHFReaderError(f"Hex string conversion failed: {e}")

    def inventory_mix_g2(self, q_value: int = 4, session: int = 0, mask_mem: int = 0,
                        mask_addr: bytes = b'\x00\x00', mask_len: int = 0,
                        mask_data: bytes = b'', mask_flag: int = 0, read_mem: int = 0,
                        read_addr: bytes = b'\x00\x00', read_len: int = 0,
                        psd: bytes = b'\x00\x00\x00\x00', target: int = 0,
                        in_ant: int = 0, scan_time: int = 20, fast_flag: int = 0) -> int:
        """
        Perform Gen2 inventory mix operation - C# style with real-time callbacks
        
        Args:
            q_value: Q value for inventory (0-15)
            session: Session number (0-3)
            mask_mem: Mask memory bank (0-3)
            mask_addr: Mask address (2 bytes)
            mask_len: Mask length in bits
            mask_data: Mask data bytes
            mask_flag: Mask flag (0-1)
            read_mem: Read memory bank (0-3)
            read_addr: Read address (2 bytes)
            read_len: Read length in words
            psd: PSD (4 bytes)
            target: Target (0-1)
            in_ant: Input antenna (0-3)
            scan_time: Scan time in 10ms units (0=default 20)
            fast_flag: Fast flag (0-1)
            
        Returns:
            Result code (0 on success, error code on failure)
            Tags are processed via callback in real-time (C# style)
        """
        if not self.is_connected:
            raise ReaderNotConnectedError("Reader is not connected")
        
        if self.is_scanning:
            raise OperationInProgressError("Inventory already in progress")
        
        try:
            # Convert parameters to bytes/bytearray for low-level API
            com_addr = bytearray([self.com_addr])
            q_value_bytes = bytes([q_value])
            session_bytes = bytes([session])
            mask_mem_bytes = bytes([mask_mem])
            mask_addr_array = bytearray(mask_addr)
            mask_len_bytes = bytes([mask_len])
            mask_data_array = bytearray(mask_data)
            mask_flag_bytes = bytes([mask_flag])
            read_mem_bytes = bytes([read_mem])
            read_addr_array = bytearray(read_addr)
            read_len_bytes = bytes([read_len])
            psd_array = bytearray(psd)
            target_bytes = bytes([target])
            in_ant_bytes = bytes([in_ant])
            scan_time_bytes = bytes([scan_time])
            fast_flag_bytes = bytes([fast_flag])
            
            # Prepare output parameters (mutable lists for pass-by-reference simulation)
            epc_list = bytearray(8192)  # Large buffer for EPC data
            ant = [0]  # Antenna number
            total_len = [0]  # Total length
            card_num = [0]  # Number of cards
            
            # Call low-level inventory_mix_g2 method
            # Tags will be processed via callback in real-time (C# style)
            result = self.uhf.inventory_mix_g2(
                com_addr, q_value_bytes, session_bytes,
                mask_mem_bytes, mask_addr_array, mask_len_bytes,
                mask_data_array, mask_flag_bytes, read_mem_bytes,
                read_addr_array, read_len_bytes, psd_array,
                target_bytes, in_ant_bytes, scan_time_bytes, fast_flag_bytes,
                epc_list, ant, total_len, card_num
            )
            
            # Update com_addr if successful
            if result == 0:
                self.com_addr = com_addr[0]
            
            logger.info(f"Inventory mix G2 completed: {card_num[0]} tags found, result={result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in inventory mix G2: {e}")
            raise UHFReaderError(f"Inventory mix G2 failed: {e}") 