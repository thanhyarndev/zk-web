from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
import threading
import time
import json
from typing import Optional, Dict, List
import serial
import logging
from uhf_reader import UHFReader

# Import configuration
from config import get_config

# Load configuration
config = get_config()

app = Flask(__name__)
app.config.from_object(config)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=True, engineio_logger=True)

# Global variables
reader: Optional[serial.Serial] = None
inventory_thread: Optional[threading.Thread] = None
stop_inventory_flag = False
detected_tags = []
inventory_stats = {"read_rate": 0, "total_count": 0}
connected_clients = set()
reader_mode_type = None  # Global variable to store reader mode type
RF_Profile = 0  # Global variable to store RF profile (exact C# equivalent)

# Global variable to store antenna count
antenna_count = 4  # Default, will be updated by api_reader_info

def determine_mode_type(reader_type_val: int) -> int:
    """
    Determine mode type from reader type value
    
    Args:
        reader_type_val: Reader type value from get_reader_information
        
    Returns:
        Mode type (0=C6, 1=R2000, 2=RRUx180, 3=9810, 4=FD)
    """
    if reader_type_val in [0x62, 0x61, 0x64, 0x66, 0x65, 0x67, 0x68]:  # C6
        return 0
    elif reader_type_val in [0x71, 0x31, 0x70, 0x72, 0x5F, 0x7F, 0x76, 0x56, 0x38,
                            0x57, 0x77, 0x39, 0x55, 0x75, 0x35, 0x33, 0x53, 0x73,
                            0x3A, 0x5A, 0x7A, 0x3B, 0x5B, 0x7B, 0x3C, 0x5C, 0x7C,
                            0x3D, 0x5D, 0x7D, 0x3E, 0x5E, 0x7E, 0x40, 0x41, 0x42,
                            0x6A, 0x6B, 0x6C]:  # RRUx180
        return 2
    elif reader_type_val == 0x11:  # 9810
        return 3
    elif reader_type_val in [0x91, 0x92, 0x93, 0x94]:  # FD
        return 4
    else:  # Default R2000
        return 1

def get_return_code_desc(result_code: int) -> str:
    """
    Get return code description - C# GetReturnCodeDesc equivalent
    
    Args:
        result_code: Error/return code from SDK
        
    Returns:
        Human-readable description of the error code
    """
    # Reader error codes
    reader_error_descriptions = {
        0x00: "API is called successfully.",
        0x01: "Tag inventory completed successfully; data delivered within inventory time.",
        0x02: "Inventory timeout.",
        0x05: "Access password error.",
        0x09: "Kill password error.",
        0x0A: "All-zero tag killing password is invalid.",
        0x0B: "Command is not supported by the tag.",
        0x0C: "All-zero tag access password is invalid for this command.",
        0x0D: "Failed to set up read protection for a protection-enabled tag.",
        0x0E: "Failed to unlock a protection-disabled tag.",
        0x10: "Some bytes stored in the tag are locked.",
        0x11: "Lock operation failed.",
        0x12: "Already locked; lock operation failed.",
        0x13: "Failed to store some preserved parameters. Configuration valid until shutdown.",
        0x14: "Modification failed.",
        0x15: "Response within the predefined inventory time.",
        0x17: "Further data is waiting to be delivered.",
        0x18: "Reader memory is full.",
        0x19: "All-zero access password is invalid or command not supported by tag.",
        0xF8: "Error detected in antenna check.",
        0xF9: "Operation failed.",
        0xFA: "Tag detected, but operation failed due to poor communication.",
        0xFB: "No tag detected.",
        0xFC: "Error code returned from tags.",
        0xFD: "Command length error.",
        0xFE: "Illegal command.",
        0xFF: "Parameter error.",
        0x30: "Communication error.",
        0x33: "Reader is busy, operation in process.",
        0x35: "Port is already opened.",
        0x37: "Invalid handle.",
    }
    # Tag error codes
    tag_error_descriptions = {
        0x00: "Other errors; non-specified error.",
        0x03: "Memory overload, location not found, or unsupported PC value.",
        0x04: "Memory is locked; unable to perform write operation.",
        0x0B: "Insufficient power supply to tag; cannot write.",
        0x0F: "Undefined or tag unsupported errors.",
    }
    if result_code in reader_error_descriptions:
        return reader_error_descriptions[result_code]
    if result_code in tag_error_descriptions:
        return tag_error_descriptions[result_code]
    return f"Unknown error code: 0x{result_code:02X}"

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Add G2 inventory debug logger
g2_debug_logger = logging.getLogger('g2_inventory_debug')
g2_debug_logger.setLevel(logging.DEBUG)
# Create file handler for G2 debug logs
g2_debug_handler = logging.FileHandler('g2_inventory_debug.log')
g2_debug_logger.setLevel(logging.DEBUG)
# Create formatter for G2 debug logs
g2_debug_formatter = logging.Formatter(
    '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s | %(message)s'
)
g2_debug_handler.setFormatter(g2_debug_formatter)
g2_debug_logger.addHandler(g2_debug_handler)

# Prevent duplicate logs
g2_debug_logger.propagate = False

def log_g2_debug(func_name: str, message: str, level: str = "INFO", **kwargs):
    """Helper function to log G2 inventory debug information with consistent formatting"""
    timestamp = time.strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
    formatted_message = f"[{timestamp}] {message}"
    
    if kwargs:
        formatted_message += f" | Params: {kwargs}"
    
    if level.upper() == "DEBUG":
        g2_debug_logger.debug(formatted_message)
    elif level.upper() == "INFO":
        g2_debug_logger.info(formatted_message)
    elif level.upper() == "WARNING":
        g2_debug_logger.warning(formatted_message)
    elif level.upper() == "ERROR":
        g2_debug_logger.error(formatted_message)
    
    # Also print to console for immediate feedback
    # print(f"[G2_DEBUG] {func_name}: {formatted_message}")

# Khởi tạo controller
reader = UHFReader()

def get_antenna_number(ant, antenna_num):
    """
    Decode antenna value to antenna number.
    For >8 antennas: direct index (ant + 1).
    For <=8 antennas: bitmask, only one bit set.
    """
    if antenna_num > 8:
        return ant + 1
    else:
        mapping = {
            0x01: 1,
            0x02: 2,
            0x04: 3,
            0x08: 4,
            0x10: 5,
            0x20: 6,
            0x40: 7,
            0x80: 8,
        }
        return mapping.get(ant, 1)

def tag_callback(tag):
    """C# style real-time tag callback - processes tags immediately as they're detected"""
    import time
    
    global antenna_count
    antenna_num = get_antenna_number(tag.antenna, antenna_count)
    
    # Convert RFIDTag object to dictionary with all properties
    tag_data = {
        'epc': tag.epc,
        'antenna': antenna_num,  # send the correct antenna number
        'rssi': tag.rssi,
        'packet_param': tag.packet_param,
        'len': tag.len,
        'phase_begin': tag.phase_begin,
        'phase_end': tag.phase_end,
        'freqkhz': tag.freqkhz,
        'device_name': tag.device_name,
        'timestamp': time.strftime("%H:%M:%S")
    }
    
    log_g2_debug("tag_callback", f"Real-time tag detected: {tag_data}", level="DEBUG")
    log_g2_debug("tag_callback", f"WebSocket clients connected: {len(socketio.server.manager.rooms)}", level="DEBUG")
    
    # Emit to WebSocket immediately (C# style real-time updates)
    socketio.emit('tag_detected', tag_data)
    
    # Add to detected tags list
    detected_tags.append(tag_data)
    
    # Update global statistics (C# style)
    inventory_stats['total_count'] = inventory_stats.get('total_count', 0) + 1
    
    # Update G2 inventory variables if they exist
    if 'g2_inventory_vars' in globals():
        g2_inventory_vars['total_tagnum'] = g2_inventory_vars.get('total_tagnum', 0) + 1

# Initialize callback after reader is created
reader.init_rfid_callback(tag_callback)

@app.route('/')
def index():
    """Trang chủ"""
    return render_template('index.html', config=config)

@app.route('/api/connect', methods=['POST'])
def api_connect():
    """API kết nối reader"""
    data = request.get_json()
    port = data.get('port', config.DEFAULT_PORT)
    baudrate = data.get('baudrate', config.DEFAULT_BAUDRATE)
    
    result = reader.open_com_port(port=port, com_addr=255, baud=baudrate)
    if result == 0:
        # Emit connection status to all connected clients
        socketio.emit('connection_status', {'connected': True, 'message': 'Connected!'})
        return jsonify({'success': True, 'message': 'Connected!'})
    else:
        error_desc = get_return_code_desc(result)
        return jsonify({'success': False, 'error': f'Connection failed: {error_desc} (code: {result})'}), 400

@app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    """API ngắt kết nối reader"""
    result = reader.close_com_port()
    # Emit connection status to all connected clients
    if result == 0:
        socketio.emit('connection_status', {'connected': False, 'message': 'Disconnected successfully'})
        return jsonify({'success': True, 'message': 'Disconnected successfully'})
    else:
        error_desc = get_return_code_desc(result)
        return jsonify({'success': False, 'error': f'Disconnection failed: {error_desc} (code: {result})'}), 400

@app.route('/api/reader_info', methods=['GET'])
def api_reader_info():
    """API lấy thông tin reader - follows C# btGetInformation_Click logic"""
    global antenna_count
    try:
        # Create parameters like C# version
        com_addr = reader.com_addr
        version_info = bytearray(2)
        reader_type = [0]
        tr_type = [0]
        dmax_fre = [0]
        dmin_fre = [0]
        power_dbm = [0]
        scan_time = [0]
        ant_cfg0 = [0]  # Antenna configuration byte 0
        beep_en = [0]
        ant_cfg1 = [0]  # Antenna configuration byte 1 (for 16-antenna readers)
        output_rep = [0]
        check_ant = [0]
        
        # Call SDK like C#: RWDev.GetReaderInformation(...)
        result = reader.get_reader_information(
            com_addr, version_info, reader_type, tr_type,
            dmax_fre, dmin_fre, power_dbm, scan_time,
            ant_cfg0, beep_en, output_rep, check_ant
        )
        
        if result != 0:
            error_desc = get_return_code_desc(result)
            return jsonify({'success': False, 'error': f'Get Reader Information failed: {error_desc} (code: {result})'}), 400
        
        # Parse data like C# code
        version_str = f"{version_info[0]:02d}.{version_info[1]:02d}"
        reader_type_val = reader_type[0]
        
        # Determine model name like C# switch statement
        model_name = "UHFREADER--" + version_str  # Default
        if reader_type_val == 0x62:
            model_name = f"UHF2882C6M--{version_str}"
        elif reader_type_val == 0x67:
            model_name = f"UHF2881C6M--{version_str}"
        elif reader_type_val == 0x73:
            model_name = f"UHF7181M--{version_str}"
        elif reader_type_val == 0x53:
            model_name = f"UHF5181M--{version_str}"
        elif reader_type_val == 0x33:
            model_name = f"UHF3181M--{version_str}"
        elif reader_type_val == 0x75:
            model_name = f"UHF7182M--{version_str}"
        elif reader_type_val == 0x55:
            model_name = f"UHF5182M--{version_str}"
        elif reader_type_val == 0x35:
            model_name = f"UHF3182M--{version_str}"
        elif reader_type_val == 0x11:
            model_name = f"UHF9810M4P--{version_str}"
        elif reader_type_val == 0x7B:
            model_name = f"UHF78C2A--{version_str}"
        elif reader_type_val == 0x5B:
            model_name = f"UHF58C2A--{version_str}"
        elif reader_type_val == 0x3B:
            model_name = f"UHF38C2A--{version_str}"
        elif reader_type_val == 0x92:
            model_name = f"UHF1682M--{version_str}"
        elif reader_type_val == 0x40:
            model_name = f"UHF7182MPH--{version_str}"
        elif reader_type_val == 0x71:
            model_name = f"UHF7180M--{version_str}"
        elif reader_type_val == 0x70:
            model_name = f"UHF5180M--{version_str}"
        elif reader_type_val == 0x31:
            model_name = f"UHF3180M--{version_str}"
        elif reader_type_val == 0x61:
            model_name = f"UHF9880C6M--{version_str}"
        elif reader_type_val == 0x64:
            model_name = f"UHF9881C6M--{version_str}"
        elif reader_type_val == 0x66:
            model_name = f"UHF9885C6M--{version_str}"
        elif reader_type_val == 0x7A:
            model_name = f"UHF7280--{version_str}"
        elif reader_type_val == 0x5A:
            model_name = f"UHF5280--{version_str}"
        elif reader_type_val == 0x3A:
            model_name = f"UHF3280--{version_str}"
        elif reader_type_val == 0x5F:
            model_name = f"UHF5281MPT--{version_str}"
        elif reader_type_val == 0x7F:
            model_name = f"UHF7281MPT--{version_str}"
        elif reader_type_val == 0x7C:
            model_name = f"UHF7281--{version_str}"
        elif reader_type_val == 0x5C:
            model_name = f"UHF5281--{version_str}"
        elif reader_type_val == 0x3C:
            model_name = f"UHF3281--{version_str}"
        elif reader_type_val == 0x7D:
            model_name = f"UHF72828M--{version_str}"
        elif reader_type_val == 0x5D:
            model_name = f"UHF52828M--{version_str}"
        elif reader_type_val == 0x3D:
            model_name = f"UHF32828M--{version_str}"
        elif reader_type_val == 0x3E:
            model_name = f"UHF3280MRL--{version_str}"
        elif reader_type_val == 0x5E:
            model_name = f"UHF5280MRL--{version_str}"
        elif reader_type_val == 0x7E:
            model_name = f"UHF3780MRL--{version_str}"
        elif reader_type_val == 0x6A:
            model_name = f"UHF353M--{version_str}"
        elif reader_type_val == 0x6B:
            model_name = f"UHF553M--{version_str}"
        elif reader_type_val == 0x6C:
            model_name = f"UHF753M--{version_str}"
        elif reader_type_val == 0x91:
            model_name = f"UHF1680M--{version_str}"
        elif reader_type_val == 0x65:
            model_name = f"UHF2899C6M--{version_str}"
        elif reader_type_val == 0x77:
            model_name = f"UHF7199M--{version_str}"
        elif reader_type_val == 0x57:
            model_name = f"UHF5199M--{version_str}"
        elif reader_type_val == 0x39:
            model_name = f"UHF3199M--{version_str}"
        elif reader_type_val == 0x94:
            model_name = f"UHF1699M--{version_str}"
        elif reader_type_val == 0x42:
            model_name = f"UHF7199MPH--{version_str}"
        elif reader_type_val == 0x68:
            model_name = f"UHF2889C6M--{version_str}"
        elif reader_type_val == 0x76:
            model_name = f"UHF7189M--{version_str}"
        elif reader_type_val == 0x56:
            model_name = f"UHF5189M--{version_str}"
        elif reader_type_val == 0x38:
            model_name = f"UHF3189M--{version_str}"
        elif reader_type_val == 0x93:
            model_name = f"UHF1689M--{version_str}"
        elif reader_type_val == 0x41:
            model_name = f"UHF7189MPH--{version_str}"
        
        # Determine mode type like C# code and set global variable
        global reader_mode_type, RF_Profile
        mode_type = determine_mode_type(reader_type_val)
        reader_mode_type = mode_type  # Set global variable for reuse
        
        # Get and store RF_Profile exactly like C# code
        # C#: byte Profile = 0; fCmdRet = RWDev.SetProfile(ref fComAdr, ref Profile, frmcomportindex);
        # C#: if (fCmdRet == 0) { RF_Profile = Profile; }
        profile_result, current_profile = reader.set_profile(profile=0)
        if profile_result == 0 and current_profile is not None:
            RF_Profile = current_profile
            logger.info(f"RF_Profile initialized: 0x{RF_Profile:02X}")
        else:
            logger.warning(f"Failed to get RF_Profile: {profile_result}")
        
        # Determine antenna count like C# code
        antenna_count = 4
        if reader_type_val in [0x11, 0x8A, 0x8B, 0x0C, 0x20, 0x62, 0x67, 0x73, 0x53, 
                              0x75, 0x55, 0x7B, 0x5B, 0x3B, 0x35, 0x33, 0x92, 0x40]:
            antenna_count = 4
        elif reader_type_val in [0x71, 0x70, 0x72, 0x0F, 0x10, 0x1A, 0x51, 0x31, 0x21,
                                0x23, 0x28, 0x36, 0x37, 0x16, 0x63, 0x64, 0x66, 0x61,
                                0x7A, 0x5A, 0x3A, 0x7C, 0x5C, 0x3C, 0x7D, 0x5D, 0x3D,
                                0x3E, 0x5E, 0x7E, 0x6A, 0x6B, 0x6C, 0x91, 0x5F, 0x7F]:
            antenna_count = 1
        elif reader_type_val in [0x27, 0x65, 0x77, 0x57, 0x39, 0x94, 0x42]:
            antenna_count = 16
        elif reader_type_val in [0x26, 0x68, 0x76, 0x56, 0x38, 0x93, 0x41]:
            antenna_count = 8
        
        # Parse frequency information like C# code
        freq_info = {}
        if dmax_fre[0] == 255 and dmin_fre[0] == 255:
            freq_info = {'band': 'Auto', 'min_freq': 0, 'max_freq': 0, 'same_freq': True}
        else:
            freq_band = ((dmax_fre[0] & 0xC0) >> 4) | (dmin_fre[0] >> 6)
            freq_info = {
                'band': freq_band,
                'dmax_fre': dmax_fre[0],
                'dmin_fre': dmin_fre[0],
                'same_freq': dmax_fre[0] == dmin_fre[0]
            }
            
            # Calculate actual frequencies based on band
            if freq_band == 1:
                freq_info['band_name'] = 'Band 1 (920.125MHz)'
                freq_info['min_freq'] = 920.125 + (dmin_fre[0] & 0x3F) * 0.25
                freq_info['max_freq'] = 920.125 + (dmax_fre[0] & 0x3F) * 0.25
            elif freq_band == 2:
                freq_info['band_name'] = 'Band 2 (902.75MHz)'
                freq_info['min_freq'] = 902.75 + (dmin_fre[0] & 0x3F) * 0.5
                freq_info['max_freq'] = 902.75 + (dmax_fre[0] & 0x3F) * 0.5
            elif freq_band == 3:
                freq_info['band_name'] = 'Band 3 (917.1MHz)'
                freq_info['min_freq'] = 917.1 + (dmin_fre[0] & 0x3F) * 0.2
                freq_info['max_freq'] = 917.1 + (dmax_fre[0] & 0x3F) * 0.2
            elif freq_band == 4:
                freq_info['band_name'] = 'Band 4 (865.1MHz)'
                freq_info['min_freq'] = 865.1 + (dmin_fre[0] & 0x3F) * 0.2
                freq_info['max_freq'] = 865.1 + (dmax_fre[0] & 0x3F) * 0.2
            elif freq_band == 8:
                freq_info['band_name'] = 'Band 8 (840.125MHz)'
                freq_info['min_freq'] = 840.125 + (dmin_fre[0] & 0x3F) * 0.25
                freq_info['max_freq'] = 840.125 + (dmax_fre[0] & 0x3F) * 0.25
            elif freq_band == 12:
                freq_info['band_name'] = 'Band 12 (902MHz)'
                freq_info['min_freq'] = 902 + (dmin_fre[0] & 0x3F) * 0.5
                freq_info['max_freq'] = 902 + (dmax_fre[0] & 0x3F) * 0.5
            elif freq_band == 0:
                freq_info['band_name'] = 'Band 0 (840MHz)'
                freq_info['min_freq'] = 840 + (dmin_fre[0] & 0x3F) * 2
                freq_info['max_freq'] = 840 + (dmax_fre[0] & 0x3F) * 2
        
        # Parse antenna configuration like C# code
        ant_config = {
            'enabled_antennas': [],
            'antenna_status': {},
            'config_byte_0': ant_cfg0[0],
            'config_hex': f"0x{ant_cfg0[0]:02X}"
        }
        
        # Parse antennas 1-8 from ant_cfg0
        for i in range(8):
            if i < antenna_count:
                antenna_num = i + 1
                enabled = (ant_cfg0[0] & (1 << i)) != 0
                ant_config['antenna_status'][f'ant{antenna_num}'] = enabled
                if enabled:
                    ant_config['enabled_antennas'].append(antenna_num)
        
        # For 16-antenna readers, note that we only have ant_cfg0
        if antenna_count == 16:
            ant_config['note'] = 'Only first 8 antennas shown (ant_cfg1 not available from SDK)'
        
        # Parse output report like C# code
        output_config = {
            'output_rep1': (output_rep[0] & 0x01) == 1,
            'output_rep2': (output_rep[0] & 0x02) == 2,
            'output_rep3': (output_rep[0] & 0x04) == 4,
            'output_rep4': (output_rep[0] & 0x08) == 8,
            'raw_value': output_rep[0]
        }
        
        data = {
            'com_addr': com_addr,
            'version_info': version_str,
            'version_bytes': bytes(version_info).hex().upper(),
            'reader_type': reader_type_val,
            'reader_type_hex': f"0x{reader_type_val:02X}",
            'model_name': model_name,
            'mode_type': mode_type,
            'antenna_count': antenna_count,
            'tr_type': tr_type[0],
            'dmax_fre': dmax_fre[0],
            'dmin_fre': dmin_fre[0],
            'power_dbm': power_dbm[0],
            'scan_time': scan_time[0],
            'ant_cfg0': ant_cfg0[0],
            'beep_en': beep_en[0],
            'output_rep': output_rep[0],
            'check_ant': check_ant[0],
            'frequency_info': freq_info,
            'antenna_config': ant_config,
            'output_config': output_config,
            'beep_status': 'Enabled' if beep_en[0] == 1 else 'Disabled',
            'antenna_check_status': 'Enabled' if check_ant[0] == 1 else 'Disabled',
            'rf_profile': RF_Profile,  # Add RF_Profile to response
            'rf_profile_hex': f"0x{RF_Profile:02X}"
        }
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        logger.error(f"Reader info error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/connection_status', methods=['GET'])
def api_connection_status():
    """API kiểm tra trạng thái kết nối"""
    is_connected = reader.is_connected if hasattr(reader, 'is_connected') else False
    return jsonify({'success': True, 'connected': is_connected})

@app.route('/api/start_inventory', methods=['POST'])
def api_start_inventory():
    """API bắt đầu inventory"""
    data = request.get_json()
    target = data.get('target', 0)
    
    try:
        # Lấy session từ param1 (exact C# GetSession logic)
        cfg_num = 0x09  # Configuration number for Param1
        cfg_data = bytearray(256)
        data_len = [0]
        result_param = reader.get_cfg_parameter(cfg_num, cfg_data, data_len)
        if result_param == 0:
            session_val = cfg_data[1]  # Return data[1] directly (exact C# logic)
        else:
            session_val = 1  # Return 1 on error (exact C# logic)
        
        # First, call select_cmd for each antenna (like C# code)
        mask_mem_val = 1       # int = EPC memory (like C# MaskMem = 1)
        mask_addr_bytes = bytes([0, 0])  # 2 bytes address (like C# MaskAdr = new byte[2])
        mask_len_val = 0       # int = no mask (like C# MaskLen = 0)
        mask_data_bytes = bytes(100)  # 100 bytes array (like C# MaskData = new byte[100])
        select_antenna = 0xFFFF  # SelectAntenna = 0xFFFF (all antennas) like C# code

        # Call select_cmd for each antenna (4 antennas like C# code)
        # Following C# code exactly: for (int m = 0; m < 4; m++)
        for antenna in range(4): 
            result = reader.select_cmd(
                antenna=select_antenna,  # SelectAntenna = 0xFFFF (all antennas)
                session=session_val,
                sel_action=0,
                mask_mem=mask_mem_val,
                mask_addr=mask_addr_bytes,
                mask_len=mask_len_val,
                mask_data=mask_data_bytes,
                truncate=0,
                antenna_num=1
            )
            log_g2_debug("api_start_inventory", f"Antenna {antenna} result: {result} session: {session_val}", level="DEBUG")
            time.sleep(0.005)  # 5ms delay like C# Thread.Sleep(5)
        
        # Clear any existing data (like C# code clears dataGridView5, epclist, etc.)
        # This is handled by the frontend when starting new inventory
        
        # Now start inventory with target
        log_g2_debug("api_start_inventory", f"Starting Fast Mode inventory with target: {target}", level="DEBUG")
        result = reader.start_inventory(target)
        log_g2_debug("api_start_inventory", f"Fast Mode inventory start result: {result}", level="DEBUG")
        
        if result == 0:
            log_g2_debug("api_start_inventory", "Fast Mode inventory started successfully", level="DEBUG")
            return jsonify({'success': True, 'message': f'Inventory đã bắt đầu (Target {"A" if target == 0 else "B"})'})
        elif result == 51:
            return jsonify({'success': False, 'message': 'Inventory is already running'}), 400
        else:
            return jsonify({'success': False, 'message': f'Failed to start inventory (code: {result})'}), 400
            
    except Exception as e:
        logger.error(f"Start inventory error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

# Global variables for G2 inventory (matching C# variables)
g2_inventory_vars = {
    'fIsInventoryScan': False,
    'toStopThread': False,
    'mythread': None,
    'Target': 0,
    'InAnt': 0,
    'Scantime': 0,
    'FastFlag': 0,
    'Qvalue': 0,
    'Session': 0,
    'total_tagnum': 0,
    'CardNum': 0,
    'NewCardNum': 0,
    'total_time': 0,
    'targettimes': 0,
    'TIDFlag': 0,
    'tidLen': 0,
    'tidAddr': 0,
    'AA_times': 0,
    'CommunicationTime': 0,
    'ReadAdr': bytearray(2),
    'Psd': bytearray(4),
    'ReadLen': 0,
    'ReadMem': 0,
    'Profile': 0,
    'readMode': 0,
    'tagrate': 0,
    'antlist': bytearray(16),
    'scanType': 0
}

@app.route('/api/start_inventory_g2', methods=['POST'])
def api_start_inventory_g2():
    """API bắt đầu inventory G2 mode - exact C# btIventoryG2_Click implementation"""
    global g2_inventory_vars, detected_tags, inventory_stats
    
    data = request.get_json()
    
    try:
        # Extract parameters from request (matching C# UI controls)
        mode_type = data.get('mode_type', 'epc')  # rb_epc, rb_tid, rb_fastid, rb_mix
        scan_time = data.get('scan_time', 0)  # com_scantime.SelectedIndex
        q_value = data.get('q_value', 4)  # com_Q.SelectedIndex
        session = data.get('session', 0)  # com_S.SelectedIndex
        target = data.get('target', 0)  # com_Target.SelectedIndex
        target_times = data.get('target_times', 1)  # text_target.Text
        enable_phase = data.get('enable_phase', False)  # check_phase.Checked
        enable_rate = data.get('enable_rate', False)  # checkBox_rate.Checked
        antennas = data.get('antennas', [1])  # check_ant1-16
        
        # Mix mode specific parameters
        mix_mem = data.get('mix_mem', 0)  # com_MixMem.SelectedIndex
        read_addr = data.get('read_addr', '0000')  # text_readadr.Text
        read_len = data.get('read_len', '04')  # text_readLen.Text
        psd = data.get('psd', '00000000')  # text_readpsd.Text
        
        # Validate mix mode parameters (exact C# validation)
        if len(read_addr) != 4 or len(read_len) != 2 or len(psd) != 8:
            return jsonify({'success': False, 'message': 'Mix inventory parameter error!!!'}), 400
        
        # Check if inventory is already running (equivalent to C# btIventoryG2.Text == "Start")
        if g2_inventory_vars['fIsInventoryScan']:
            return jsonify({'success': False, 'message': 'Inventory is already running'}), 400
        
        # Set mix mode parameters if rb_mix.Checked (exact C# logic)
        if mode_type == 'mix':
            g2_inventory_vars['ReadMem'] = mix_mem
            g2_inventory_vars['ReadAdr'] = bytearray.fromhex(read_addr)
            g2_inventory_vars['ReadLen'] = int(read_len, 16)
            g2_inventory_vars['Psd'] = bytearray.fromhex(psd)
        
        # Clear counters and lists (exact C# logic)
        g2_inventory_vars['total_tagnum'] = 0
        g2_inventory_vars['AA_times'] = 0
        detected_tags.clear()
        inventory_stats = {
            'total_tags': 0,
            'total_time': 0,
            'commands_sent': 0,
            'commands_successful': 0
        }
        
        # Set scan time (exact C# logic)
        g2_inventory_vars['Scantime'] = scan_time
        
        # Set Q value with rate flag if enabled (exact C# logic)
        if enable_rate:
            g2_inventory_vars['Qvalue'] = q_value | 0x80
        else:
            g2_inventory_vars['Qvalue'] = q_value
        
        # Set profile for ModeType 2 (exact C# logic)
        # Use global reader_mode_type instead of calling get_reader_information
        global reader_mode_type
        if reader_mode_type is None:
            # If global mode type is not set, get it from reader info
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
            
            reader_info_result = reader.get_reader_information(
                reader.com_addr, version_info, reader_type, tr_type,
                dmax_fre, dmin_fre, power_dbm, scan_time,
                ant_cfg0, beep_en, output_rep, check_ant
            )
            if reader_info_result == 0:
                reader_mode_type = determine_mode_type(reader_type[0])
        
        if reader_mode_type == 2:
            g2_inventory_vars['Profile'] = RF_Profile | 0xC0
            result, new_profile = reader.set_profile(profile=g2_inventory_vars['Profile'])
            if result == 0 and new_profile is not None:
                g2_inventory_vars['Profile'] = new_profile
            else:
                logger.warning(f"Failed to set profile: {result}")
        
        # Set read mode based on session (exact C# logic)
        if session == 4:
            g2_inventory_vars['readMode'] = 255
        elif session < 4:
            g2_inventory_vars['readMode'] = session
        elif session == 5:
            g2_inventory_vars['readMode'] = 254
        elif session == 6:
            g2_inventory_vars['readMode'] = 253
        
        # Store mode_type for inventory_worker to use
        g2_inventory_vars['mode_type'] = mode_type
        
        # Set scan type and flags based on mode (exact C# logic)
        if mode_type == 'epc':
            g2_inventory_vars['TIDFlag'] = 0
            g2_inventory_vars['scanType'] = 0
        elif mode_type == 'tid':
            g2_inventory_vars['TIDFlag'] = 1
            g2_inventory_vars['tidAddr'] = int(read_addr, 16) & 0x00FF
            g2_inventory_vars['tidLen'] = int(read_len, 16)
            g2_inventory_vars['scanType'] = 1
        elif mode_type == 'fastid':
            g2_inventory_vars['TIDFlag'] = 0
            g2_inventory_vars['Qvalue'] = q_value | 0x20
            g2_inventory_vars['scanType'] = 2
        else:  # mix mode
            g2_inventory_vars['scanType'] = 3
        
        # Add phase flag if enabled (exact C# logic)
        if enable_phase:
            g2_inventory_vars['Qvalue'] |= 0x10
        
        # Set target times and start time (exact C# logic)
        g2_inventory_vars['targettimes'] = target_times
        g2_inventory_vars['enable_target_times'] = data.get('enable_target_times', True)  # Default to True like C#
        g2_inventory_vars['total_time'] = int(time.time() * 1000)  # System.Environment.TickCount equivalent
        
        # Set inventory scan flag and button state (exact C# logic)
        g2_inventory_vars['fIsInventoryScan'] = False
        g2_inventory_vars['toStopThread'] = False
        
        # Build antenna configuration (exact C# logic with proper antenna mapping)
        g2_inventory_vars['antlist'] = bytearray(16)
        select_antenna = 0
        
        # Map antenna numbers to C# style bit positions
        for ant_num in antennas:
            if 1 <= ant_num <= 16:
                g2_inventory_vars['antlist'][ant_num - 1] = 1
                g2_inventory_vars['InAnt'] = 0x80 + (ant_num - 1)
                select_antenna |= (1 << (ant_num - 1))
        
        # Call PresetTarget (exact C# logic)
        preset_target(g2_inventory_vars['readMode'], select_antenna)
        
        # Set target (exact C# logic)
        g2_inventory_vars['Target'] = target
        
        # Debug logging to verify all parameters are set correctly
        logger.info(f"[DEBUG] api_start_inventory_g2() - Final parameter verification:")
        logger.info(f"  Mode type: {mode_type}")
        logger.info(f"  Scan time: {g2_inventory_vars['Scantime']} (={g2_inventory_vars['Scantime']*100}ms)")
        logger.info(f"  Q value: {g2_inventory_vars['Qvalue']}")
        logger.info(f"  Session: {g2_inventory_vars['Session']}")
        logger.info(f"  Target: {g2_inventory_vars['Target']}")
        logger.info(f"  Target times: {g2_inventory_vars['targettimes']}")
        logger.info(f"  Enable target times: {g2_inventory_vars.get('enable_target_times', True)}")
        logger.info(f"  Antennas: {antennas}")
        logger.info(f"  Ant list: {[i for i, val in enumerate(g2_inventory_vars['antlist']) if val == 1]}")
        logger.info(f"  InAnt: {g2_inventory_vars['InAnt']} (0x{g2_inventory_vars['InAnt']:02X})")
        logger.info(f"  TID flag: {g2_inventory_vars['TIDFlag']}")
        logger.info(f"  TID addr: {g2_inventory_vars['tidAddr']} (0x{g2_inventory_vars['tidAddr']:02X})")
        logger.info(f"  TID len: {g2_inventory_vars['tidLen']}")
        logger.info(f"  Scan type: {g2_inventory_vars['scanType']}")
        logger.info(f"  Read mode: {g2_inventory_vars['readMode']}")
        
        # Start inventory thread (exact C# logic)
        if not g2_inventory_vars['fIsInventoryScan']:
            g2_inventory_vars['mythread'] = threading.Thread(target=inventory_worker, daemon=True)
            g2_inventory_vars['mythread'].start()
            g2_inventory_vars['fIsInventoryScan'] = True
        
        return jsonify({
            'success': True, 
            'message': f'G2 Mode inventory started successfully ({mode_type.upper()})',
            'parameters': {
                'mode_type': mode_type,
                'scan_type': g2_inventory_vars['scanType'],
                'q_value': g2_inventory_vars['Qvalue'],
                'session': session,
                'target': g2_inventory_vars['Target'],
                'antennas': antennas,
                'scan_time': g2_inventory_vars['Scantime'],
                'target_times': g2_inventory_vars['targettimes']
            }
        })
            
    except Exception as e:
        logger.error(f"Start G2 inventory error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

def preset_target(read_mode, select_antenna):
    """Exact C# PresetTarget implementation"""
    global g2_inventory_vars
    
    log_g2_debug("preset_target", "=== FUNCTION START ===", level="INFO")
    log_g2_debug("preset_target", f"Input parameters", level="INFO", 
                 read_mode=read_mode, select_antenna=f"0x{select_antenna:04X}")
    log_g2_debug("preset_target", f"Current Session before preset", level="INFO", 
                 current_session=g2_inventory_vars.get('Session', 'undefined'))
    
    cur_session = 0
    if read_mode > 0:
        log_g2_debug("preset_target", "Read mode > 0, proceeding with target setup", level="INFO")
        
        mask_mem = 1
        mask_addr = bytearray(2)
        mask_len = 0
        mask_data = bytearray(100)
        
        log_g2_debug("preset_target", "Getting reader information for ModeType", level="DEBUG")
        
        # Use global reader_mode_type instead of calling get_reader_information
        global reader_mode_type
        reader_type_val = None
        reader_info_result = 0
        
        if reader_mode_type is None:
            # Get ModeType from reader info if not already set
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
            
            reader_info_result = reader.get_reader_information(
                reader.com_addr, version_info, reader_type, tr_type,
                dmax_fre, dmin_fre, power_dbm, scan_time,
                ant_cfg0, beep_en, output_rep, check_ant
            )
            
            log_g2_debug("preset_target", f"Reader info result", level="DEBUG", 
                         result=reader_info_result, reader_type=reader_type[0] if reader_info_result == 0 else "N/A")
            
            if reader_info_result == 0:
                reader_mode_type = determine_mode_type(reader_type[0])
                reader_type_val = reader_type[0]
        
        mode_type_val = reader_mode_type
        log_g2_debug("preset_target", f"Mode type determined", level="INFO", 
                     mode_type=mode_type_val)
            
        # Determine AntennaNum from reader type
        if reader_type_val is not None:
            antenna_num = 1  # Default
            if reader_type_val in [0x11, 0x8A, 0x8B, 0x0C, 0x20, 0x62, 0x67, 0x73, 0x53, 
                              0x75, 0x55, 0x7B, 0x5B, 0x3B, 0x35, 0x33, 0x92, 0x40]:
                antenna_num = 4
            elif reader_type_val in [0x27, 0x65, 0x77, 0x57, 0x39, 0x94, 0x42]:
                antenna_num = 16
            elif reader_type_val in [0x26, 0x68, 0x76, 0x56, 0x38, 0x93, 0x41]:
                antenna_num = 8
        else:
            # If we don't have reader info, use a default antenna number based on mode type
            if mode_type_val == 0:  # C6
                antenna_num = 4
            elif mode_type_val == 2:  # RRUx180
                antenna_num = 1  # Default for RRUx180
            elif mode_type_val == 3:  # 9810
                antenna_num = 4
            elif mode_type_val == 4:  # FD
                antenna_num = 16  # Default for FD
            else:  # R2000
                antenna_num = 1
            
            log_g2_debug("preset_target", f"Using default antenna number based on mode type", level="INFO", 
                         antenna_num=antenna_num, mode_type=mode_type_val)
        
        log_g2_debug("preset_target", f"Antenna number determined", level="INFO", 
                     antenna_num=antenna_num)
        
        if (read_mode == 254 or read_mode == 253) and (mode_type_val == 2):
            log_g2_debug("preset_target", "Processing RRUx180 special mode (253/254)", level="INFO")
            
            if g2_inventory_vars['Session'] == 254:
                g2_inventory_vars['Session'] = 253
                cur_session = 2
                log_g2_debug("preset_target", "Switching from Session 254 to 253", level="INFO")
            else:
                g2_inventory_vars['Session'] = 254
                cur_session = 3
                log_g2_debug("preset_target", "Switching to Session 254", level="INFO")
            
            if read_mode == 253:
                g2_inventory_vars['Profile'] = 0xC1
                log_g2_debug("preset_target", "Setting Profile to 0xC1 for read_mode 253", level="INFO")
            else:
                g2_inventory_vars['Profile'] = 0xC5
                log_g2_debug("preset_target", "Setting Profile to 0xC5 for read_mode 254", level="INFO")
            
            result, new_profile = reader.set_profile(profile=g2_inventory_vars['Profile'])
            if result == 0 and new_profile is not None:
                g2_inventory_vars['Profile'] = new_profile
            log_g2_debug("preset_target", f"Set profile result", level="INFO", 
                         profile=f"0x{g2_inventory_vars['Profile']:02X}", result=result)
            
            if result != 0:
                log_g2_debug("preset_target", f"Set profile failed", level="WARNING", 
                             result=result)
            
        elif read_mode == 255:
            log_g2_debug("preset_target", "Processing Fast Mode (255) - using both session 2 and 3", level="INFO")
            
            cur_session = 2
            g2_inventory_vars['Session'] = read_mode
            
            log_g2_debug("preset_target", "Sending select_cmd for session 2 (2 iterations)", level="DEBUG")
            for m in range(2):
                result = reader.select_cmd(
                    antenna=select_antenna, session=cur_session, sel_action=0,
                    mask_mem=mask_mem, mask_addr=bytes(mask_addr), mask_len=mask_len,
                    mask_data=bytes(mask_data), truncate=0, antenna_num=antenna_num
                )
                log_g2_debug("preset_target", f"Session 2 select_cmd iteration {m+1}", level="DEBUG", 
                             result=result)
                time.sleep(0.005)  # Thread.Sleep(5)
            
            cur_session = 3
            log_g2_debug("preset_target", "Sending select_cmd for session 3 (2 iterations)", level="DEBUG")
            for m in range(2):
                result = reader.select_cmd(
                    antenna=select_antenna, session=cur_session, sel_action=0,
                    mask_mem=mask_mem, mask_addr=bytes(mask_addr), mask_len=mask_len,
                    mask_data=bytes(mask_data), truncate=0, antenna_num=antenna_num
                )
                log_g2_debug("preset_target", f"Session 3 select_cmd iteration {m+1}", level="DEBUG", 
                             result=result)
                time.sleep(0.005)  # Thread.Sleep(5)
                
        elif read_mode < 4:
            log_g2_debug("preset_target", f"Processing standard session mode {read_mode}", level="INFO")
            
            cur_session = read_mode
            g2_inventory_vars['Session'] = cur_session
            
            log_g2_debug("preset_target", f"Sending select_cmd for session {cur_session} (4 iterations)", level="DEBUG")
            for m in range(4):
                result = reader.select_cmd(
                    antenna=select_antenna, session=cur_session, sel_action=0,
                    mask_mem=mask_mem, mask_addr=bytes(mask_addr), mask_len=mask_len,
                    mask_data=bytes(mask_data), truncate=0, antenna_num=antenna_num
                )
                log_g2_debug("preset_target", f"Session {cur_session} select_cmd iteration {m+1}", level="DEBUG", 
                             result=result)
                time.sleep(0.005)  # Thread.Sleep(5)
    else:
        log_g2_debug("preset_target", "Read mode <= 0, setting session directly", level="INFO")
        g2_inventory_vars['Session'] = read_mode
    
    log_g2_debug("preset_target", f"Final session value", level="INFO", 
                 final_session=g2_inventory_vars['Session'])
    log_g2_debug("preset_target", "=== FUNCTION END ===", level="INFO")

def inventory_worker():
    """Exact C# inventory() method implementation"""
    global g2_inventory_vars, detected_tags, reader_mode_type
    
    log_g2_debug("inventory_worker", "=== FUNCTION START ===", level="INFO")
    log_g2_debug("inventory_worker", "Initial state", level="INFO", 
                 session=g2_inventory_vars.get('Session'), 
                 mode_type=g2_inventory_vars.get('mode_type'),
                 target=g2_inventory_vars.get('Target'),
                 to_stop_thread=g2_inventory_vars.get('toStopThread'))
    
    g2_inventory_vars['fIsInventoryScan'] = True
    cycle_count = 0
    
    while not g2_inventory_vars['toStopThread']:
        cycle_count += 1
        log_g2_debug("inventory_worker", f"=== CYCLE {cycle_count} START ===", level="DEBUG")
        
        try:
            if g2_inventory_vars['Session'] == 255:
                log_g2_debug("inventory_worker", "Auto session mode (Session 255)", level="INFO")
                # Auto session mode (exact C# logic)
                g2_inventory_vars['FastFlag'] = 0
                log_g2_debug("inventory_worker", "FastFlag set to 0 for auto mode", level="DEBUG")
                
                if g2_inventory_vars.get('mode_type') == 'mix':
                    log_g2_debug("inventory_worker", "Calling flash_mix_g2()", level="INFO")
                    flash_mix_g2()
                else:
                    log_g2_debug("inventory_worker", "Calling flash_g2()", level="INFO")
                    flash_g2()
            else:
                log_g2_debug("inventory_worker", f"Manual session mode (Session {g2_inventory_vars['Session']})", level="INFO")
                # Manual session mode (exact C# logic)
                # Use global reader_mode_type to determine antenna number
                
                # Determine antenna number based on mode type (AntennaNum in C#)
                global antenna_count
                antenna_num = antenna_count
                
                log_g2_debug("inventory_worker", f"Antenna cycling", level="INFO", 
                             antenna_num=antenna_num, session=g2_inventory_vars['Session'], mode_type=reader_mode_type)
                
                # Cycle through antennas (exact C# logic)
                for m in range(antenna_num):
                    g2_inventory_vars['InAnt'] = m | 0x80  # InAnt = (byte)(m | 0x80)
                    g2_inventory_vars['FastFlag'] = 1      # FastFlag = 1
                    
                    log_g2_debug("inventory_worker", f"Processing antenna {m+1}", level="DEBUG", 
                                 in_ant=g2_inventory_vars['InAnt'], fast_flag=g2_inventory_vars['FastFlag'],
                                 ant_enabled=g2_inventory_vars['antlist'][m] == 1)
                    
                    if g2_inventory_vars['antlist'][m] == 1:
                        # Handle session 2 and 3 target switching (exact C# logic)
                        if (g2_inventory_vars['Session'] > 1 and g2_inventory_vars['Session'] < 4):  # s2,s3
                            log_g2_debug("inventory_worker", f"Checking target switching", level="DEBUG", 
                                         aa_times=g2_inventory_vars['AA_times'], target_times=g2_inventory_vars['targettimes'])
                            
                            # Exact C# logic: if ((check_num.Checked) && (AA_times + 1 > targettimes))
                            if (g2_inventory_vars.get('enable_target_times', True) and 
                                (g2_inventory_vars['AA_times'] + 1 > g2_inventory_vars['targettimes'])):
                                g2_inventory_vars['Target'] = 1 - g2_inventory_vars['Target']  # Target = Convert.ToByte(1 - Target)
                                g2_inventory_vars['AA_times'] = 0
                                
                                log_g2_debug("inventory_worker", f"Target switched", level="INFO", 
                                             new_target=g2_inventory_vars['Target'])
                        
                        # Call appropriate inventory function based on mode (exact C# logic)
                        if g2_inventory_vars.get('mode_type') == 'mix':  # if (rb_mix.Checked)
                            log_g2_debug("inventory_worker", f"Calling flash_mix_g2() for antenna {m+1}", level="INFO")
                            flash_mix_g2()
                        else:
                            log_g2_debug("inventory_worker", f"Calling flash_g2() for antenna {m+1}", level="INFO")
                            flash_g2()
                            log_g2_debug("inventory_worker", f"Calling preset_profile() for antenna {m+1}", level="INFO")
                            preset_profile()
                    else:
                        log_g2_debug("inventory_worker", f"Antenna {m+1} disabled, skipping", level="DEBUG")
            
            log_g2_debug("inventory_worker", f"=== CYCLE {cycle_count} END ===", level="DEBUG")
            # Small delay between cycles (exact C# Thread.Sleep(5))
            time.sleep(0.005)
            
        except Exception as ex:
            log_g2_debug("inventory_worker", f"Exception in cycle {cycle_count}", level="ERROR", 
                         exception=str(ex))
            # Continue running despite errors (exact C# behavior)
            time.sleep(0.1)
    
    log_g2_debug("inventory_worker", "Main loop ended, starting cleanup", level="INFO")
    
    # Cleanup when thread stops (exact C# logic)
    # Use global reader_mode_type instead of calling get_reader_information
    log_g2_debug("inventory_worker", f"Cleanup mode type", level="DEBUG", 
                 mode_type=reader_mode_type)
    
    if reader_mode_type == 2:  # if (ModeType == 2)
        g2_inventory_vars['Profile'] = RF_Profile | 0xC0  # Profile = (byte)(RF_Profile | 0xC0)
        result, new_profile = reader.set_profile(profile=g2_inventory_vars['Profile'])
        if result == 0 and new_profile is not None:
            g2_inventory_vars['Profile'] = new_profile
        
        log_g2_debug("inventory_worker", f"Profile restoration", level="INFO", 
                     new_profile=g2_inventory_vars['Profile'], result=result)
        
        if result != 0:
            log_g2_debug("inventory_worker", f"Failed to restore profile", level="WARNING", 
                         result=result)
    
    # Final cleanup (exact C# logic)
    g2_inventory_vars['fIsInventoryScan'] = False
    g2_inventory_vars['mythread'] = None
    
    log_g2_debug("inventory_worker", "=== FUNCTION END ===", level="INFO")

def flash_g2():
    """Exact C# flash_G2() method implementation"""
    global g2_inventory_vars, detected_tags, reader_mode_type
    
    log_g2_debug("flash_g2", "=== FUNCTION START ===", level="INFO")
    
    ant = 0
    tag_num = 0
    total_len = 0
    epc = bytearray(50000)
    mask_mem = 0
    mask_addr = bytearray(2)
    mask_len = 0
    mask_data = bytearray(100)
    mask_flag = 0
    
    cbtime = int(time.time() * 1000)  # System.Environment.TickCount equivalent
    g2_inventory_vars['CardNum'] = 0
    g2_inventory_vars['tagrate'] = 0
    g2_inventory_vars['NewCardNum'] = 0
    
    log_g2_debug("flash_g2", "Parameters for inventory_g2 call", level="INFO", 
                 q_value=g2_inventory_vars['Qvalue'],
                 session=g2_inventory_vars['Session'],
                 scan_time=g2_inventory_vars['Scantime'],
                 scan_time_ms=g2_inventory_vars['Scantime']*100,
                 target=g2_inventory_vars['Target'],
                 target_name="Target A" if g2_inventory_vars['Target'] == 0 else "Target B",
                 in_ant=g2_inventory_vars['InAnt'],
                 in_ant_hex=f"0x{g2_inventory_vars['InAnt']:02X}",
                 tid_flag=g2_inventory_vars['TIDFlag'],
                 tid_addr=g2_inventory_vars['tidAddr'],
                 tid_addr_hex=f"0x{g2_inventory_vars['tidAddr']:02X}",
                 tid_len=g2_inventory_vars['tidLen'],
                 mode_type=g2_inventory_vars.get('mode_type', 'unknown'))
    
    # Call inventory_g2 (exact C# RWDev.Inventory_G2 call)
    # Pass all parameters including TID parameters that were set in api_start_inventory_g2
    log_g2_debug("flash_g2", "Calling reader.inventory_g2()", level="INFO")
    tags = reader.inventory_g2(
        q_value=g2_inventory_vars['Qvalue'],
        session=g2_inventory_vars['Session'],
        scan_time=g2_inventory_vars['Scantime'],
        target=g2_inventory_vars['Target'],
        in_ant=g2_inventory_vars['InAnt'],
        tid_flag=g2_inventory_vars['TIDFlag'],
        tid_addr=g2_inventory_vars['tidAddr'],
        tid_len=g2_inventory_vars['tidLen'],
        fast_flag=g2_inventory_vars['FastFlag']
    )
    
    # C# style error handling - check if tags is a list (success) or error code
    if isinstance(tags, list):
        result = 0  # Success
        g2_inventory_vars['CardNum'] = len(tags)
        
        log_g2_debug("flash_g2", f"Inventory successful", level="INFO", 
                     tags_found=len(tags), result=result)
        
        # Process detected tags
        for i, tag in enumerate(tags):
            global antenna_count
            antenna_num = get_antenna_number(tag.antenna, antenna_count)
            tag_data = {
                'epc': tag.epc,
                'rssi': tag.rssi,
                'antenna': antenna_num,
                'timestamp': time.strftime("%H:%M:%S"),
                'phase_begin': getattr(tag, 'phase_begin', 0),
                'phase_end': getattr(tag, 'phase_end', 0),
                'freqkhz': getattr(tag, 'freqkhz', 0)
            }
            log_g2_debug("flash_g2", f"Processing tag {i+1}", level="DEBUG", 
                         epc=tag.epc, rssi=tag.rssi, antenna=tag.antenna)
            
            # Emit to WebSocket immediately (C# style real-time updates)
            socketio.emit('tag_detected', tag_data)
            detected_tags.append(tag_data)
            g2_inventory_vars['total_tagnum'] += 1
    else:
        # tags is actually an error code
        result = tags
        error_desc = get_return_code_desc(result)
        log_g2_debug("flash_g2", f"Inventory failed", level="ERROR", 
                     result=result, error_desc=error_desc)
        g2_inventory_vars['CardNum'] = 0
    
    cmd_time = int(time.time() * 1000) - cbtime
    
    log_g2_debug("flash_g2", f"Command execution time", level="DEBUG", 
                 cmd_time=cmd_time, result=result)
    
    # Handle result codes (exact C# logic)
    if result not in [0x01, 0x02, 0xF8, 0xF9, 0xEE, 0xFF]:
        # Handle connection issues (exact C# logic)
        log_g2_debug("flash_g2", f"Non-standard inventory result", level="WARNING", 
                     result=result)
        # Note: C# has TCP reconnection logic here, but we don't have TCP support
    
    if result == 0x30:
        g2_inventory_vars['CardNum'] = 0
        log_g2_debug("flash_g2", "No tags found (0x30), setting CardNum to 0", level="INFO")
    
    if g2_inventory_vars['CardNum'] == 0:
        if g2_inventory_vars['Session'] > 1:
            g2_inventory_vars['AA_times'] += 1
            log_g2_debug("flash_g2", f"AA_times incremented (no tags found)", level="DEBUG", 
                         aa_times=g2_inventory_vars['AA_times'])
    else:
        log_g2_debug("flash_g2", f"Tags found ({g2_inventory_vars['CardNum']} tags), checking for RRUx180 special handling", level="DEBUG")
        
        log_g2_debug("flash_g2", f"Reader type check", level="DEBUG", 
                     mode_type=reader_mode_type,
                     read_mode=g2_inventory_vars['readMode'], new_card_num=g2_inventory_vars['NewCardNum'])
        
        # Exact C# logic: if ((ModeType == 2) && (readMode == 253 || readMode == 254) && (NewCardNum == 0))
        if (reader_mode_type == 2) and (g2_inventory_vars['readMode'] == 253 or g2_inventory_vars['readMode'] == 254) and (g2_inventory_vars['NewCardNum'] == 0):
            g2_inventory_vars['AA_times'] += 1
            log_g2_debug("flash_g2", f"RRUx180 special case: AA_times incremented", level="DEBUG", 
                         aa_times=g2_inventory_vars['AA_times'])
        else:
            g2_inventory_vars['AA_times'] = 0
            log_g2_debug("flash_g2", f"AA_times reset to 0", level="DEBUG")
    
    # Calculate tag rate (exact C# logic)
    if result in [1, 2, 0xFB, 0x26]:
        if cmd_time > g2_inventory_vars['CommunicationTime']:
            cmd_time = cmd_time - g2_inventory_vars['CommunicationTime']
        if cmd_time > 0:
            g2_inventory_vars['tagrate'] = (g2_inventory_vars['CardNum'] * 1000) // cmd_time
            log_g2_debug("flash_g2", f"Tag rate calculated", level="DEBUG", 
                         tagrate=g2_inventory_vars['tagrate'], card_num=g2_inventory_vars['CardNum'], cmd_time=cmd_time)
    
    # Send WebSocket updates (equivalent to C# SendMessage)
    socketio.emit('inventory_status', {
        'cmd_ret': result,
        'tag_rate': g2_inventory_vars['tagrate'],
        'total_tags': g2_inventory_vars['total_tagnum'],
        'cmd_time': cmd_time,
        'card_num': g2_inventory_vars['CardNum']
    })
    
    log_g2_debug("flash_g2", "=== FUNCTION END ===", level="INFO")

def flash_mix_g2():
    """Exact C# flashmix_G2() method implementation"""
    global g2_inventory_vars, detected_tags
    
    ant = 0
    tag_num = 0
    total_len = 0
    epc = bytearray(50000)
    mask_mem = 0
    mask_addr = bytearray(2)
    mask_len = 0
    mask_data = bytearray(100)
    mask_flag = 0
    
    cbtime = int(time.time() * 1000)  # System.Environment.TickCount equivalent
    g2_inventory_vars['CardNum'] = 0
    g2_inventory_vars['NewCardNum'] = 0
    
    # Call inventory_mix_g2 (exact C# RWDev.InventoryMix_G2 call)
    # Tags will be processed via callback in real-time (C# style)
    
    # Reset tag counter for this scan
    initial_tag_count = g2_inventory_vars['total_tagnum']
    
    # Call inventory with C# style error code handling
    result = reader.inventory_mix_g2(
        q_value=g2_inventory_vars['Qvalue'],
        session=g2_inventory_vars['Session'],
        mask_mem=0,  # Default for mix mode
        mask_addr=bytes(2),  # Default empty mask
        mask_len=0,  # Default no mask
        mask_data=bytes(100),  # Default empty mask data
        mask_flag=0,  # Default no mask flag
        read_mem=g2_inventory_vars['ReadMem'],
        read_addr=bytes(g2_inventory_vars['ReadAdr']),  # Convert bytearray to bytes
        read_len=g2_inventory_vars['ReadLen'],
        psd=bytes(g2_inventory_vars['Psd']),  # Convert bytearray to bytes
        target=g2_inventory_vars['Target'],
        in_ant=g2_inventory_vars['InAnt'],
        scan_time=g2_inventory_vars['Scantime'],
        fast_flag=g2_inventory_vars['FastFlag']
    )
    
    # Calculate tags found in this scan (C# style)
    tags_found_this_scan = g2_inventory_vars['total_tagnum'] - initial_tag_count
    g2_inventory_vars['CardNum'] = tags_found_this_scan
    
    # C# style error handling - check specific error codes
    if result != 0:
        error_desc = get_return_code_desc(result)
        logger.error(f"Inventory Mix G2 failed: {error_desc} (code: {result})")
        g2_inventory_vars['CardNum'] = 0
    
    cmd_time = int(time.time() * 1000) - cbtime
    
    # Handle result codes (exact C# logic)
    if result not in [0x01, 0x02, 0xF8, 0xF9, 0xEE, 0xFF]:
        # Handle connection issues (exact C# logic)
        logger.warning(f"Non-standard mix inventory result: {result}")
    
    g2_inventory_vars['NewCardNum'] = g2_inventory_vars['CardNum']
    
    if g2_inventory_vars['CardNum'] == 0:
        if g2_inventory_vars['Session'] > 1:
            g2_inventory_vars['AA_times'] += 1
    else:
        g2_inventory_vars['AA_times'] = 0
    
    # Calculate tag rate (exact C# logic)
    if result in [1, 2, 0xFB, 0x26]:
        if cmd_time > g2_inventory_vars['CommunicationTime']:
            cmd_time = cmd_time - g2_inventory_vars['CommunicationTime']
        if cmd_time > 0:
            g2_inventory_vars['tagrate'] = (g2_inventory_vars['CardNum'] * 1000) // cmd_time
    
    # Send WebSocket updates (equivalent to C# SendMessage)
    socketio.emit('inventory_status', {
        'cmd_ret': result,
        'tag_rate': g2_inventory_vars['tagrate'],
        'total_tags': g2_inventory_vars['total_tagnum'],
        'cmd_time': cmd_time,
        'card_num': g2_inventory_vars['CardNum']
    })

def preset_profile():
    """Exact C# PresetProfile() method implementation"""
    global g2_inventory_vars, reader_mode_type
    
    log_g2_debug("preset_profile", "=== FUNCTION START ===", level="INFO")
    log_g2_debug("preset_profile", "Current state", level="INFO", 
                 read_mode=g2_inventory_vars.get('readMode'),
                 profile=g2_inventory_vars.get('Profile'),
                 tagrate=g2_inventory_vars.get('tagrate'),
                 card_num=g2_inventory_vars.get('CardNum'),
                 new_card_num=g2_inventory_vars.get('NewCardNum'),
                 aa_times=g2_inventory_vars.get('AA_times'),
                 target_times=g2_inventory_vars.get('targettimes'))
    
    log_g2_debug("preset_profile", f"Mode type determined", level="INFO", 
                 mode_type=reader_mode_type)
    
    if (g2_inventory_vars['readMode'] == 254 or g2_inventory_vars['readMode'] == 253) and (reader_mode_type == 2):
            log_g2_debug("preset_profile", "Processing RRUx180 profile optimization", level="INFO")
            
            if (g2_inventory_vars['Profile'] == 0x01) and (g2_inventory_vars['readMode'] == 253):
                log_g2_debug("preset_profile", "Checking Profile 0x01 with readMode 253", level="DEBUG", 
                             tagrate=g2_inventory_vars['tagrate'], card_num=g2_inventory_vars['CardNum'])
                
                if g2_inventory_vars['tagrate'] < 150 or g2_inventory_vars['CardNum'] < 150:
                    old_profile = g2_inventory_vars['Profile']
                    g2_inventory_vars['Profile'] = 0xC5
                    result, new_profile = reader.set_profile(profile=g2_inventory_vars['Profile'])
                    if result == 0 and new_profile is not None:
                        g2_inventory_vars['Profile'] = new_profile
                    
                    log_g2_debug("preset_profile", f"Profile changed from 0x01 to 0xC5", level="INFO", 
                                 old_profile=f"0x{old_profile:02X}", new_profile=f"0x{g2_inventory_vars['Profile']:02X}", result=result)
                    
                    if result != 0:
                        log_g2_debug("preset_profile", f"Set profile failed", level="WARNING", 
                                     result=result)
                        
            elif g2_inventory_vars['Profile'] == 0x05:
                log_g2_debug("preset_profile", "Checking Profile 0x05", level="DEBUG", 
                             new_card_num=g2_inventory_vars['NewCardNum'])
                
                if g2_inventory_vars['NewCardNum'] < 5:
                    old_profile = g2_inventory_vars['Profile']
                    g2_inventory_vars['Profile'] = 0xCD
                    result, new_profile = reader.set_profile(profile=g2_inventory_vars['Profile'])
                    if result == 0 and new_profile is not None:
                        g2_inventory_vars['Profile'] = new_profile
                                
                    log_g2_debug("preset_profile", f"Profile changed from 0x05 to 0xCD", level="INFO", 
                                 old_profile=f"0x{old_profile:02X}", new_profile=f"0x{g2_inventory_vars['Profile']:02X}", result=result)
                    
                    if result != 0:
                        log_g2_debug("preset_profile", f"Set profile failed", level="WARNING", 
                                     result=result)
                    
                    g2_inventory_vars['AA_times'] = 0
                    log_g2_debug("preset_profile", "AA_times reset to 0", level="DEBUG")
                    
            elif g2_inventory_vars['Profile'] == 0x0D:
                log_g2_debug("preset_profile", "Checking Profile 0x0D", level="DEBUG", 
                             new_card_num=g2_inventory_vars['NewCardNum'], aa_times=g2_inventory_vars['AA_times'])
                
                if g2_inventory_vars['NewCardNum'] > 20:
                    old_profile = g2_inventory_vars['Profile']
                    g2_inventory_vars['Profile'] = 0xC5
                    result, new_profile = reader.set_profile(profile=g2_inventory_vars['Profile'])
                    if result == 0 and new_profile is not None:
                        g2_inventory_vars['Profile'] = new_profile
                    
                    log_g2_debug("preset_profile", f"Profile changed from 0x0D to 0xC5 (high card count)", level="INFO", 
                                 old_profile=f"0x{old_profile:02X}", new_profile=f"0x{g2_inventory_vars['Profile']:02X}", result=result)
                    
                    if result != 0:
                        log_g2_debug("preset_profile", f"Set profile failed", level="WARNING", 
                                     result=result)

                elif g2_inventory_vars['AA_times'] >= g2_inventory_vars['targettimes']:
                    old_profile = g2_inventory_vars['Profile']
                    old_target = g2_inventory_vars['Target']
                    
                    if g2_inventory_vars['readMode'] == 254:
                        g2_inventory_vars['Profile'] = 0xC5
                        log_g2_debug("preset_profile", "Setting profile to 0xC5 for readMode 254", level="INFO")
                    elif g2_inventory_vars['readMode'] == 253:
                        g2_inventory_vars['Profile'] = 0xC1
                        log_g2_debug("preset_profile", "Setting profile to 0xC1 for readMode 253", level="INFO")
                    
                    result, new_profile = reader.set_profile(profile=g2_inventory_vars['Profile'])
                    if result == 0 and new_profile is not None:
                        g2_inventory_vars['Profile'] = new_profile
                                
                    log_g2_debug("preset_profile", f"Profile changed due to AA_times threshold", level="INFO", 
                                 old_profile=f"0x{old_profile:02X}", new_profile=f"0x{g2_inventory_vars['Profile']:02X}", result=result)
                    
                    if result != 0:
                        log_g2_debug("preset_profile", f"Set profile failed", level="WARNING", 
                                     result=result)
                    
                    g2_inventory_vars['AA_times'] = 0
                    g2_inventory_vars['Target'] = 1 - g2_inventory_vars['Target']  # A/B state switch
                    
                    log_g2_debug("preset_profile", f"AA_times reset and target switched", level="INFO", 
                                 aa_times=g2_inventory_vars['AA_times'], old_target=old_target, new_target=g2_inventory_vars['Target'])
                else:
                    log_g2_debug("preset_profile", "No profile change needed", level="DEBUG")
    else:
        log_g2_debug("preset_profile", "Not RRUx180 or not special readMode, skipping profile optimization", level="DEBUG")

    log_g2_debug("preset_profile", "=== FUNCTION END ===", level="INFO")

@app.route('/api/stop_inventory', methods=['POST'])
def api_stop_inventory():
    """API dừng inventory"""
    try:
        result = reader.stop_inventory()
        if result == 0:
            logger.info("Tags inventory stopped successfully")
            return {"success": True, "message": "Tags inventory stopped successfully"}
        else:
            logger.error(f"Failed to stop tags inventory (code: {result})")
            return {"success": False, "message": f'Failed to stop tags inventory (code: {result})'}
    except Exception as e:
        logger.error(f"Stop tags inventory error: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}

@app.route('/api/stop_inventory_g2', methods=['POST'])
def api_stop_inventory_g2():
    """API dừng inventory G2 mode - exact C# logic"""
    global g2_inventory_vars
    
    try:
        # Set stop flag (exact C# logic)
        g2_inventory_vars['toStopThread'] = True
        
        # Stop inventory immediately (exact C# RWDev.StopImmediately call)
        result = reader.stop_inventory()
        
        # Wait for thread to stop (exact C# logic)
        if g2_inventory_vars['mythread'] and g2_inventory_vars['mythread'].is_alive():
            g2_inventory_vars['mythread'].join(timeout=2)
        
        # Reset flags (exact C# logic)
        g2_inventory_vars['fIsInventoryScan'] = False
        g2_inventory_vars['mythread'] = None
        
        if result == 0:
            return jsonify({'success': True, 'message': 'G2 Mode inventory stopped successfully'})
        else:
            error_desc = get_return_code_desc(result)
            logger.warning(f"Stop inventory returned code {result}: {error_desc}")
            return jsonify({'success': True, 'message': f'G2 Mode inventory stopped (warning: {error_desc})'})
            
    except Exception as e:
        logger.error(f"Stop G2 inventory error: {e}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500

@app.route('/api/set_power', methods=['POST'])
def api_set_power():
    """API thiết lập công suất"""
    data = request.get_json()
    power = data.get('power', config.DEFAULT_ANTENNA_POWER)
    # UHFReader.set_rf_power does not support preserve_config
    result = reader.set_rf_power(power)
    if result == 0:
        return jsonify({'success': True, 'message': f'Power set successfully: {power} dBm'})
    else:
        return jsonify({'success': False, 'message': f'Failed to set power: {get_return_code_desc(result)} (code: {result})'}), 400

@app.route('/api/set_ant_multiplexing', methods=['POST'])
def api_set_ant_multiplexing():
    """
    Configure antenna settings based on selected antennas list
    """
    
    data = request.get_json()
    antennas = data.get('selectedAntennas')
    save = data.get('save')
    global antenna_count

    ant = 0
    ant1 = 0
    set_once = 0

    for antenna_num in antennas:
        if 1 <= antenna_num <= 8:
            ant |= (1 << (antenna_num - 1))
        elif 9 <= antenna_num <= 16:
            ant1 |= (1 << (antenna_num - 9))

    if antenna_count == 4:
        if not save:
            set_once = 0x80
        
        result = reader.set_antenna_multiplexing(ant | set_once)
        
    elif antenna_count == 8:
        if save:
            set_once = 0  
        else:
            set_once = 1 
        
        result = reader.set_antenna(set_once, ant1, ant)
        
    elif antenna_count == 16:
        if save:
            set_once = 0  
        else:
            set_once = 1  
        
        result = reader.set_antenna(set_once, ant1, ant)
        
    if result == 0:
        return jsonify({'success': True, 'message': f'Set  successfully'})
    else:
        return jsonify({'success': False, 'message': f'Failed to set antenna multiplexing: {get_return_code_desc(result)} (code: {result})'}), 400


@app.route('/api/get_antenna_power', methods=['GET'])
def api_get_antenna_power():
    """API lấy công suất antennas"""
    try:
        power_bytes = reader.get_antenna_power()
        # Convert bytes to dict: {1: power1, 2: power2, ...}
        power_levels = {i + 1: b for i, b in enumerate(power_bytes) if b != 0}
        return jsonify({'success': True, 'data': power_levels})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/get_tags', methods=['GET'])
def api_get_tags():
    """API lấy danh sách tags đã phát hiện"""
    return jsonify({
        "success": True,
        "data": detected_tags,
        "stats": inventory_stats
    })

@app.route('/api/write_epc_g2', methods=['POST'])
def api_write_epc_g2():
    """API to write EPC to a tag (G2) - matches C# btWriteEPC_G2_Click logic"""
    try:

        data = request.get_json()
        write_epc = data.get("epc", "")
        password = data.get("password", "")
        
        # Validation: Password must be 8 hex digits
        if len(password) < 8:
            return jsonify({"success": False, "message": "Access Password Less Than 8 digit!"}), 400

        # Validation: EPC must be non-empty and length is a multiple of 4
        if (len(write_epc) % 4) != 0 or len(write_epc) == 0:
            return jsonify({
                "success": False,
                "message": "Please input Data by words in hexadecimal form! For example: 1234, 12345678"
            }), 400

        # Call backend write_epc_g2 (UHFReader)
        try:
            result = reader.write_epc_g2(password, write_epc)
            if result == 0:
                return jsonify({"success": True, "message": "Write EPC success"})
            else:
                return jsonify({"success": False, "message": f"Write EPC failed: {get_return_code_desc(result)} (code: {result})"}), 400
        except Exception as e:
            return jsonify({"success": False, "message": f"Write EPC failed: {str(e)}"}), 400

    except Exception as e:
        logger.error(f"/api/write_epc_g2 error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

@app.route('/api/debug', methods=['GET'])
def api_debug():
    """API debug info"""
    try:
        data = {
            "is_connected": reader.is_connected,
            "inventory_thread_alive": inventory_thread.is_alive() if inventory_thread else False,
            "stop_inventory_flag": stop_inventory_flag,
            "detected_tags_count": len(detected_tags),
            "inventory_stats": inventory_stats,
            "recent_tags": detected_tags[-10:] if detected_tags else []  # 10 tags gần nhất
        }
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Debug API error: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}

@app.route('/api/reset_reader', methods=['POST'])
def api_reset_reader():
    """API reset reader"""
    try:
        # Dừng inventory nếu đang chạy
        if hasattr(reader, 'is_scanning') and reader.is_scanning:
            logger.info("Dừng inventory trước khi reset reader")
            reader.stop_inventory()
            time.sleep(1.0)  # Đợi thread dừng hoàn toàn
        
        # Clear data
        detected_tags.clear()
        inventory_stats = {"read_rate": 0, "total_count": 0}
        
        # Reset reader nếu đã kết nối
        if getattr(reader, 'is_connected', False):
            try:
                logger.info("Đang reset reader...")
                # Clear buffers if available
                if hasattr(reader, 'uhf') and hasattr(reader.uhf, 'serial_port') and reader.uhf.serial_port:
                    try:
                        reader.uhf.serial_port.reset_input_buffer()
                        reader.uhf.serial_port.reset_output_buffer()
                        time.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Buffer clear warning: {e}")
                # Gửi lệnh stop inventory nhiều lần để đảm bảo reader dừng hoàn toàn
                for i in range(3):
                    try:
                        reader.stop_inventory()
                        time.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Stop command attempt {i+1} failed: {e}")
                # Đợi reader ổn định
                time.sleep(0.5)
                # Clear buffers một lần nữa
                if hasattr(reader, 'uhf') and hasattr(reader.uhf, 'serial_port') and reader.uhf.serial_port:
                    try:
                        reader.uhf.serial_port.reset_input_buffer()
                        reader.uhf.serial_port.reset_output_buffer()
                        time.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Buffer clear warning: {e}")
                logger.info("Reader reset completed successfully")
            except Exception as e:
                logger.warning(f"Reader reset warning: {e}")
        logger.info("Reader reset completed")
        return {"success": True, "message": "Đã reset reader thành công"}
    except Exception as e:
        logger.error(f"Reset reader error: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}

@socketio.on('connect')
def handle_connect():
    """Xử lý khi client kết nối WebSocket"""
    logger.info(f"🔌 WebSocket client connected: {request.sid}")
    log_g2_debug("handle_connect", f"WebSocket client connected: {request.sid}", level="DEBUG")
    socketio.emit('status', {'message': 'Connected to server'})
    connected_clients.add(request.sid)
    log_g2_debug("handle_connect", f"Total connected clients: {len(connected_clients)}", level="DEBUG")

@socketio.on('disconnect')
def handle_disconnect():
    """Xử lý khi client ngắt kết nối WebSocket"""
    logger.info(f"🔌 WebSocket client disconnected: {request.sid}")
    log_g2_debug("handle_disconnect", f"WebSocket client disconnected: {request.sid}", level="DEBUG")
    connected_clients.remove(request.sid)
    log_g2_debug("handle_disconnect", f"Total connected clients: {len(connected_clients)}", level="DEBUG")

@socketio.on('message')
def handle_message(message):
    """Xử lý message từ client"""
    logger.info(f"📨 Received WebSocket message: {message}")

# Parameter Configuration API Endpoints
@app.route('/api/set_param1', methods=['POST'])
def api_set_param1():
    """API thiết lập parameter 1 (Q-value, Session, Phase) - cfgNum = 0x09"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Not connected to reader"})
        
        data = request.get_json()
        q_value = int(data.get("q_value", 4))
        session = int(data.get("session", 0))
        phase = bool(data.get("phase", False))
        save = bool(data.get("save", False))
        
        # Convert to bytes exactly like C# code
        data_bytes = bytearray(2)
        data_bytes[0] = q_value & 0x0F  # Q-value (lower 4 bits)
        if phase:
            data_bytes[0] |= 0x10  # Set phase bit (like C# data[0] |= 0x10)
        data_bytes[1] = session & 0xFF  # Session
        
        # Set opt based on save checkbox (like C# opt = 0x00 if save, else 0x01)
        opt = 0x00 if save else 0x01
        cfg_num = 0x09  # Configuration number for Param1
        
        # Call the actual SDK function
        result = reader.set_cfg_parameter(opt, cfg_num, bytes(data_bytes))
        
        if result == 0:
            logger.info(f"Param1 set successfully: Q={q_value}, Session={session}, Phase={phase}, Save={save}")
            return jsonify({
                "success": True,
                "message": f"Parameter 1 set successfully (Q={q_value}, Session=S{session}, Phase={phase})"
            })
        else:
            logger.error(f"Param1 set failed with code: {result}")
            return jsonify({"success": False, "message": f"Set failed: {get_return_code_desc(result)} (code: {result})"})
            
    except Exception as e:
        logger.error(f"Set Param1 error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/get_param1', methods=['GET'])
def api_get_param1():
    """API lấy parameter 1 (Q-value, Session, Phase) - cfgNum = 0x09"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Not connected to reader"})
        
        cfg_num = 0x09  # Configuration number for Param1
        cfg_data = bytearray(256)  # Buffer for configuration data
        data_len = [0]  # Will be updated with actual data length
        
        # Call the actual SDK function
        result = reader.get_cfg_parameter(cfg_num, cfg_data, data_len)
        
        if result == 0 and data_len[0] >= 2:
            # Parse data exactly like C# code
            q_value = cfg_data[0] & 0x0F  # Lower 4 bits (like C# data[0] & 0x0F)
            phase = (cfg_data[0] & 0x10) > 0  # Phase bit (like C# (data[0] & 0x10) > 0)
            session = cfg_data[1] if cfg_data[1] < 4 else 0  # Session (like C# data[1] < 4)
            
            logger.info(f"Param1 retrieved: Q={q_value}, Session={session}, Phase={phase}")
            return jsonify({
                "success": True,
                "data": {
                    "q_value": q_value,
                    "session": session,
                    "phase": phase
                }
            })
        else:
            logger.error(f"Param1 get failed with code: {result}")
            return jsonify({"success": False, "message": f"Get failed: {get_return_code_desc(result)} (code: {result})"})
            
    except Exception as e:
        logger.error(f"Get Param1 error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/set_tid_param', methods=['POST'])
def api_set_tid_param():
    """API thiết lập TID parameter - cfgNum = 0x0A"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Not connected to reader"})
        
        data = request.get_json()
        start_addr = data.get("start_addr", "00")
        length = data.get("length", "00")
        save = bool(data.get("save", False))
        
        # Convert hex strings to bytes exactly like C# code
        start_addr_byte = int(start_addr, 16)
        length_byte = int(length, 16)
        
        # Convert to bytes
        data_bytes = bytearray(2)
        data_bytes[0] = start_addr_byte  # Like C# data[0] = Convert.ToByte(txt_mtidaddr.Text, 16)
        data_bytes[1] = length_byte      # Like C# data[1] = Convert.ToByte(txt_Mtidlen.Text, 16)
        
        # Set opt based on save checkbox
        opt = 0x00 if save else 0x01
        cfg_num = 0x0A  # Configuration number for TID Param
        
        # Call the actual SDK function
        result = reader.set_cfg_parameter(opt, cfg_num, bytes(data_bytes))
        
        if result == 0:
            logger.info(f"TID Param set successfully: Start=0x{start_addr}, Length=0x{length}, Save={save}")
            return jsonify({
                "success": True,
                "message": f"TID parameter set successfully (Start=0x{start_addr}, Length=0x{length})"
            })
        else:
            logger.error(f"TID Param set failed with code: {result}")
            return jsonify({"success": False, "message": f"Set failed: {get_return_code_desc(result)} (code: {result})"})
            
    except Exception as e:
        logger.error(f"Set TID Param error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/get_tid_param', methods=['GET'])
def api_get_tid_param():
    """API lấy TID parameter - cfgNum = 0x0A"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Not connected to reader"})
        
        cfg_num = 0x0A  # Configuration number for TID Param
        cfg_data = bytearray(256)  # Buffer for configuration data
        data_len = [0]  # Will be updated with actual data length
        
        # Call the actual SDK function
        result = reader.get_cfg_parameter(cfg_num, cfg_data, data_len)
        
        if result == 0 and data_len[0] >= 2:
            # Parse data exactly like C# code
            start_addr = f"{cfg_data[0]:02x}"  # Like C# Convert.ToString(data[0], 16).PadLeft(2, '0')
            length = f"{cfg_data[1]:02x}"      # Like C# Convert.ToString(data[1], 16).PadLeft(2, '0')
            
            logger.info(f"TID Param retrieved: Start=0x{start_addr}, Length=0x{length}")
            return jsonify({
                "success": True,
                "data": {
                    "start_addr": start_addr,
                    "length": length
                }
            })
        else:
            logger.error(f"TID Param get failed with code: {result}")
            return jsonify({"success": False, "message": f"Get failed: {get_return_code_desc(result)} (code: {result})"})
            
    except Exception as e:
        logger.error(f"Get TID Param error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/set_mask_param', methods=['POST'])
def api_set_mask_param():
    """API thiết lập Mask parameter - cfgNum = 0x0B"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Not connected to reader"})
        
        data = request.get_json()
        mask_type = int(data.get("mask_type", 1))  # 1=EPC, 2=TID, 3=User
        start_addr = data.get("start_addr", "0020")
        length = data.get("length", "00")
        mask_data = data.get("data", "")
        save = bool(data.get("save", False))
        
        # Convert hex strings to integers
        start_addr_int = int(start_addr, 16)
        length_int = int(length, 16)
        
        # Build data array exactly like C# code
        data_bytes = bytearray()
        
        # Add mask type (like C# data[len] = 1/2/3)
        data_bytes.append(mask_type)
        
        # Add start address (2 bytes, like C# data[len] = (byte)(MaskAddr >> 8), data[len+1] = (byte)(MaskAddr & 255))
        data_bytes.append((start_addr_int >> 8) & 0xFF)
        data_bytes.append(start_addr_int & 0xFF)
        
        # Add length (like C# data[len] = (byte)MaskLen)
        data_bytes.append(length_int)
        
        # Add mask data if length > 0
        if length_int > 0 and mask_data:
            # Convert hex string to bytes
            mask_data_bytes = bytes.fromhex(mask_data.replace(" ", ""))
            data_len_bytes = (length_int + 7) // 8  # Like C# (MaskLen + 7) / 8
            
            if len(mask_data_bytes) >= data_len_bytes:
                data_bytes.extend(mask_data_bytes[:data_len_bytes])
            else:
                return jsonify({"success": False, "message": "Mask data length insufficient"})
        
        # Set opt based on save checkbox
        opt = 0x00 if save else 0x01
        cfg_num = 0x0B  # Configuration number for Mask Param
        
        # Call the actual SDK function
        result = reader.set_cfg_parameter(opt, cfg_num, bytes(data_bytes))
        
        if result == 0:
            logger.info(f"Mask Param set successfully: Type={mask_type}, Start=0x{start_addr}, Length=0x{length}, Data={mask_data}, Save={save}")
            return jsonify({
                "success": True,
                "message": f"Mask parameter set successfully (Type={mask_type}, Start=0x{start_addr}, Length=0x{length})"
            })
        else:
            logger.error(f"Mask Param set failed with code: {result}")
            return jsonify({"success": False, "message": f"Set failed: {get_return_code_desc(result)} (code: {result})"})
            
    except Exception as e:
        logger.error(f"Set Mask Param error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/get_mask_param', methods=['GET'])
def api_get_mask_param():
    """API lấy Mask parameter - cfgNum = 0x0B"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Not connected to reader"})
        
        cfg_num = 0x0B  # Configuration number for Mask Param
        cfg_data = bytearray(256)  # Buffer for configuration data
        data_len = [0]  # Will be updated with actual data length
        
        # Call the actual SDK function
        result = reader.get_cfg_parameter(cfg_num, cfg_data, data_len)
        
        if result == 0 and data_len[0] >= 4:
            # Parse data exactly like C# code
            mask_type = cfg_data[0]  # Like C# data[0] == 1/2/3
            
            # Start address (2 bytes, like C# data[1] * 256 + data[2])
            start_addr = f"{cfg_data[1] * 256 + cfg_data[2]:04x}"  # Like C# Convert.ToString(data[1] * 256 + data[2], 16).PadLeft(4, '0')
            
            # Length (like C# data[3])
            length = f"{cfg_data[3]:02x}"  # Like C# Convert.ToString(data[3], 16).PadLeft(2, '0')
            
            # Mask data (remaining bytes, like C# Array.Copy(data, 4, daw, 0, daw.Length))
            mask_data = ""
            if cfg_data[3] > 0 and data_len[0] > 4:
                mask_data_bytes = cfg_data[4:data_len[0]]
                mask_data = mask_data_bytes.hex().upper()  # Like C# ByteArrayToHexString(daw)
            
            logger.info(f"Mask Param retrieved: Type={mask_type}, Start=0x{start_addr}, Length=0x{length}, Data={mask_data}")
            return jsonify({
                "success": True,
                "data": {
                    "mask_type": mask_type,
                    "start_addr": start_addr,
                    "length": length,
                    "data": mask_data
                }
            })
        else:
            logger.error(f"Mask Param get failed with code: {result}")
            return jsonify({"success": False, "message": f"Get failed: {get_return_code_desc(result)} (code: {result})"})
            
    except Exception as e:
        logger.error(f"Get Mask Param error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/get_profile', methods=['GET'])
def api_get_profile():
    """API lấy current profile - exact C# button1_Click_1 implementation"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Not connected to reader"})
        
        # Get current profile exactly like C#: byte Profile = 0; RWDev.SetProfile(ref fComAdr, ref Profile, frmcomportindex);
        profile_result, current_profile = reader.set_profile(profile=0)
        
        if profile_result != 0:
            error_desc = get_return_code_desc(profile_result)
            logger.error(f"Get RF-Link Profile failed: {error_desc}")
            return jsonify({"success": False, "message": f"Get RF-Link Profile failed: {error_desc}"})
        
        # Map profile to comboBox index based on ModeType (exact C# logic)
        global reader_mode_type, RF_Profile
        selected_index = -1
        
        if reader_mode_type == 0:  # C6
            if current_profile == 0x10: selected_index = 0
            elif current_profile == 0x11: selected_index = 1
            elif current_profile == 0x12: selected_index = 2
            elif current_profile == 0x13: selected_index = 3
            elif current_profile == 0x14: selected_index = 4
        elif reader_mode_type == 1:  # R2000
            if current_profile == 0x00: selected_index = 0
            elif current_profile == 0x01: selected_index = 1
            elif current_profile == 0x02: selected_index = 2
            elif current_profile == 0x03: selected_index = 3
        elif reader_mode_type == 2:  # RRUx180
            # For RRUx180, the profile may have 0x80 bit set, so mask it out for comparison
            profile_without_bit7 = current_profile & 0x7F  # Remove bit 7 (0x80)
            if profile_without_bit7 == 11: selected_index = 0
            elif profile_without_bit7 == 1: selected_index = 1
            elif profile_without_bit7 == 15: selected_index = 2
            elif profile_without_bit7 == 12: selected_index = 3
            elif profile_without_bit7 == 3: selected_index = 4
            elif profile_without_bit7 == 5: selected_index = 5
            elif profile_without_bit7 == 7: selected_index = 6
            elif profile_without_bit7 == 13: selected_index = 7
            elif profile_without_bit7 == 50: selected_index = 8
            elif profile_without_bit7 == 51: selected_index = 9
            elif profile_without_bit7 == 52: selected_index = 10
            elif profile_without_bit7 == 53: selected_index = 11
            RF_Profile = current_profile  # Update global RF_Profile like C#
        elif reader_mode_type == 4:  # FD
            # For FD, the profile may have 0x80 bit set, so mask it out for comparison
            profile_without_bit7 = current_profile & 0x7F  # Remove bit 7 (0x80)
            if profile_without_bit7 == 0x20: selected_index = 0
            elif profile_without_bit7 == 0x21: selected_index = 1
            elif profile_without_bit7 == 0x22: selected_index = 2
            elif profile_without_bit7 == 0x23: selected_index = 3
            elif profile_without_bit7 == 0x24: selected_index = 4
            elif profile_without_bit7 == 0x25: selected_index = 5
            elif profile_without_bit7 == 0x26: selected_index = 6
            elif profile_without_bit7 == 0x27: selected_index = 7
            elif profile_without_bit7 == 0x28: selected_index = 8
            RF_Profile = current_profile  # Update global RF_Profile like C#
        
        logger.info(f"Get RF-Link Profile success: Profile=0x{current_profile:02X}, Index={selected_index}")
        return jsonify({
            "success": True,
            "data": {
                "profile": current_profile,
                "profile_hex": f"0x{current_profile:02X}",
                "selected_index": selected_index,
                "mode_type": reader_mode_type
            }
        })
        
    except Exception as e:
        logger.error(f"Get profile error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/set_profile', methods=['POST'])
def api_set_profile():
    """API thiết lập profile - exact C# button2_Click_1 implementation"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Not connected to reader"})
        
        data = request.get_json()
        selected_index = data.get('selected_index', 0)
        
        # Calculate profile value based on ModeType and selected index (exact C# logic)
        global reader_mode_type, RF_Profile
        profile_value = 0
        
        if reader_mode_type == 0:  # C6
            if selected_index == 0: profile_value = 0x90
            elif selected_index == 1: profile_value = 0x91
            elif selected_index == 2: profile_value = 0x92
            elif selected_index == 3: profile_value = 0x93
            elif selected_index == 4: profile_value = 0x94
        elif reader_mode_type == 1:  # R2000
            if selected_index == 0: profile_value = 0x80
            elif selected_index == 1: profile_value = 0x81
            elif selected_index == 2: profile_value = 0x82
            elif selected_index == 3: profile_value = 0x83
        elif reader_mode_type == 2:  # RRUx180
            if selected_index == 0: profile_value = 11
            elif selected_index == 1: profile_value = 1
            elif selected_index == 2: profile_value = 15
            elif selected_index == 3: profile_value = 12
            elif selected_index == 4: profile_value = 3
            elif selected_index == 5: profile_value = 5
            elif selected_index == 6: profile_value = 7
            elif selected_index == 7: profile_value = 13
            elif selected_index == 8: profile_value = 50
            elif selected_index == 9: profile_value = 51
            elif selected_index == 10: profile_value = 52
            elif selected_index == 11: profile_value = 53
            profile_value |= 0x80  # Profile |= 0x80 like C#
        elif reader_mode_type == 4:  # FD
            if selected_index == 0: profile_value = 0x20
            elif selected_index == 1: profile_value = 0x21
            elif selected_index == 2: profile_value = 0x22
            elif selected_index == 3: profile_value = 0x23
            elif selected_index == 4: profile_value = 0x24
            elif selected_index == 5: profile_value = 0x25
            elif selected_index == 6: profile_value = 0x26
            elif selected_index == 7: profile_value = 0x27
            elif selected_index == 8: profile_value = 0x28
            profile_value |= 0x80  # Profile |= 0x80 like C#
        
        # Set profile exactly like C#: RWDev.SetProfile(ref fComAdr, ref Profile, frmcomportindex);
        result, new_profile = reader.set_profile(profile=profile_value)
        
        if result != 0:
            error_desc = get_return_code_desc(result)
            logger.error(f"Set RF-Link Profile failed: {error_desc}")
            return jsonify({"success": False, "message": f"Set RF-Link Profile failed: {error_desc}"})
        
        # Update global RF_Profile like C#: RF_Profile = Profile;
        RF_Profile = new_profile if new_profile is not None else profile_value
        
        logger.info(f"Set RF-Link Profile success: Profile=0x{RF_Profile:02X}")
        return jsonify({
            "success": True,
            "message": f"Set RF-Link Profile success: 0x{RF_Profile:02X}",
            "data": {
                "profile": RF_Profile,
                "profile_hex": f"0x{RF_Profile:02X}",
                "selected_index": selected_index,
                "mode_type": reader_mode_type
            }
        })
        
    except Exception as e:
        logger.error(f"Set profile error: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

if __name__ == '__main__':
    logger.info(f"Starting RFID Web Control Panel on {config.HOST}:{config.PORT}")
    socketio.run(app, debug=config.DEBUG, host=config.HOST, port=config.PORT) 