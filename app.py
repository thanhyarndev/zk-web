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

def get_return_code_desc(result_code: int) -> str:
    """
    Get return code description - C# GetReturnCodeDesc equivalent
    
    Args:
        result_code: Error/return code from SDK
        
    Returns:
        Human-readable description of the error code
    """
    error_descriptions = {
        0: "Success",
        1: "Inventory completed successfully",
        2: "Inventory completed with tags found",
        3: "Inventory continuing",
        4: "Inventory completed with errors",
        0xFB: "CRC error",
        0x26: "Command not supported",
        0x30: "No tags found",
        0x31: "Communication error",
        0x32: "Parameter error",
        0x33: "Memory error",
        0x34: "Antenna error",
        0x35: "Power error",
        0x36: "Frequency error",
        0x37: "Protocol error",
        0x38: "Timeout error",
        0x39: "Buffer overflow",
        0x3A: "Authentication error",
        0x3B: "Access denied",
        0x3C: "Device busy",
        0x3D: "Device not ready",
        0x3E: "Device not found",
        0x3F: "Device error",
        0x40: "Invalid command",
        0x41: "Invalid parameter",
        0x42: "Invalid address",
        0x43: "Invalid length",
        0x44: "Invalid data",
        0x45: "Invalid checksum",
        0x46: "Invalid response",
        0x47: "Invalid state",
        0x48: "Operation timeout",
        0x49: "Operation failed",
        0x4A: "Operation cancelled",
        0x4B: "Operation not supported",
        0x4C: "Operation in progress",
        0x4D: "Operation completed",
        0x4E: "Operation aborted",
        0x4F: "Operation suspended",
        0x50: "Operation resumed",
        0x51: "Operation already in progress",
        0x52: "Operation not in progress",
        0x53: "Already connected",
        0x54: "Not connected",
        0x55: "Connection failed",
        0x56: "Connection lost",
        0x57: "Connection timeout",
        0x58: "Connection refused",
        0x59: "Connection reset",
        0x5A: "Connection closed",
        0x5B: "Connection error",
        0x5C: "Port not available",
        0x5D: "Port in use",
        0x5E: "Port error",
        0x5F: "Port timeout",
        0x60: "Port not found",
        0x61: "Port access denied",
        0x62: "Port busy",
        0x63: "Port not ready",
        0x64: "Port not open",
        0x65: "Port already open",
        0x66: "Port configuration error",
        0x67: "Port communication error",
        0x68: "Port hardware error",
        0x69: "Port software error",
        0x6A: "Port driver error",
        0x6B: "Port firmware error",
        0x6C: "Port protocol error",
        0x6D: "Port format error",
        0x6E: "Port parity error",
        0x6F: "Port stop bits error",
        0x70: "Port data bits error",
        0x71: "Port baud rate error",
        0x72: "Port flow control error",
        0x73: "Port handshake error",
        0x74: "Port buffer error",
        0x75: "Port queue error",
        0x76: "Port interrupt error",
        0x77: "Port DMA error",
        0x78: "Port memory error",
        0x79: "Port register error",
        0x7A: "Port status error",
        0x7B: "Port control error",
        0x7C: "Port mode error",
        0x7D: "Port type error",
        0x7E: "Port version error",
        0x7F: "Port revision error",
        0x80: "Port serial number error",
        0x81: "Port model error",
        0x82: "Port manufacturer error",
        0x83: "Port description error",
        0x84: "Port location error",
        0x85: "Port class error",
        0x86: "Port subclass error",
        0x87: "Port interface error",
        0x88: "Port endpoint error",
        0x89: "Port configuration descriptor error",
        0x8A: "Port interface descriptor error",
        0x8B: "Port endpoint descriptor error",
        0x8C: "Port string descriptor error",
        0x8D: "Port device descriptor error",
        0x8E: "Port setup packet error",
        0x8F: "Port data packet error",
        0x90: "Port status packet error",
        0x91: "Port token packet error",
        0x92: "Port handshake packet error",
        0x93: "Port special packet error",
        0x94: "Port reserved packet error",
        0x95: "Port vendor specific packet error",
        0x96: "Port class specific packet error",
        0x97: "Port standard packet error",
        0x98: "Port extended packet error",
        0x99: "Port isochronous packet error",
        0x9A: "Port bulk packet error",
        0x9B: "Port interrupt packet error",
        0x9C: "Port control packet error",
        0x9D: "Port data toggle error",
        0x9E: "Port sequence error",
        0x9F: "Port stall error",
        0xA0: "Port nak error",
        0xA1: "Port ack error",
        0xA2: "Port nyet error",
        0xA3: "Port split error",
        0xA4: "Port ping error",
        0xA5: "Port pong error",
        0xA6: "Port prepare error",
        0xA7: "Port complete error",
        0xA8: "Port start split error",
        0xA9: "Port middle split error",
        0xAA: "Port end split error",
        0xAB: "Port short packet error",
        0xAC: "Port long packet error",
        0xAD: "Port zero length packet error",
        0xAE: "Port maximum packet size error",
        0xAF: "Port minimum packet size error",
        0xB0: "Port packet size error",
        0xB1: "Port packet count error",
        0xB2: "Port packet interval error",
        0xB3: "Port packet delay error",
        0xB4: "Port packet timeout error",
        0xB5: "Port packet retry error",
        0xB6: "Port packet abort error",
        0xB7: "Port packet cancel error",
        0xB8: "Port packet suspend error",
        0xB9: "Port packet resume error",
        0xBA: "Port packet reset error",
        0xBB: "Port packet clear error",
        0xBC: "Port packet flush error",
        0xBD: "Port packet purge error",
        0xBE: "Port packet close error",
        0xBF: "Port packet open error",
        0xC0: "Port packet read error",
        0xC1: "Port packet write error",
        0xC2: "Port packet control error",
        0xC3: "Port packet status error",
        0xC4: "Port packet configuration error",
        0xC5: "Port packet interface error",
        0xC6: "Port packet endpoint error",
        0xC7: "Port packet descriptor error",
        0xC8: "Port packet setup error",
        0xC9: "Port packet data error",
        0xCA: "Port packet token error",
        0xCB: "Port packet handshake error",
        0xCC: "Port packet special error",
        0xCD: "Port packet reserved error",
        0xCE: "Port packet vendor specific error",
        0xCF: "Port packet class specific error",
        0xD0: "Port packet standard error",
        0xD1: "Port packet extended error",
        0xD2: "Port packet isochronous error",
        0xD3: "Port packet bulk error",
        0xD4: "Port packet interrupt error",
        0xD5: "Port packet control error",
        0xD6: "Port packet data toggle error",
        0xD7: "Port packet sequence error",
        0xD8: "Port packet stall error",
        0xD9: "Port packet nak error",
        0xDA: "Port packet ack error",
        0xDB: "Port packet nyet error",
        0xDC: "Port packet split error",
        0xDD: "Port packet ping error",
        0xDE: "Port packet pong error",
        0xDF: "Port packet prepare error",
        0xE0: "Port packet complete error",
        0xE1: "Port packet start split error",
        0xE2: "Port packet middle split error",
        0xE3: "Port packet end split error",
        0xE4: "Port packet short error",
        0xE5: "Port packet long error",
        0xE6: "Port packet zero length error",
        0xE7: "Port packet maximum size error",
        0xE8: "Port packet minimum size error",
        0xE9: "Port packet size mismatch error",
        0xEA: "Port packet count mismatch error",
        0xEB: "Port packet interval mismatch error",
        0xEC: "Port packet delay mismatch error",
        0xED: "Port packet timeout mismatch error",
        0xEE: "Port packet retry mismatch error",
        0xEF: "Port packet abort mismatch error",
        0xF0: "Port packet cancel mismatch error",
        0xF1: "Port packet suspend mismatch error",
        0xF2: "Port packet resume mismatch error",
        0xF3: "Port packet reset mismatch error",
        0xF4: "Port packet clear mismatch error",
        0xF5: "Port packet flush mismatch error",
        0xF6: "Port packet purge mismatch error",
        0xF7: "Port packet close mismatch error",
        0xF8: "Port packet open mismatch error",
        0xF9: "Port packet read mismatch error",
        0xFA: "Port packet write mismatch error",
        0xFB: "Port packet control mismatch error",
        0xFC: "Port packet status mismatch error",
        0xFD: "Port packet configuration mismatch error",
        0xFE: "Port packet interface mismatch error",
        0xFF: "Port packet endpoint mismatch error"
    }
    
    return error_descriptions.get(result_code, f"Unknown error code: 0x{result_code:02X}")

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Khởi tạo controller
reader = UHFReader()

def tag_callback(tag):
    """C# style real-time tag callback - processes tags immediately as they're detected"""
    import time
    
    # Convert RFIDTag object to dictionary with all properties
    tag_data = {
        'epc': tag.epc,
        'antenna': tag.antenna,
        'rssi': tag.rssi,
        'packet_param': tag.packet_param,
        'len': tag.len,
        'phase_begin': tag.phase_begin,
        'phase_end': tag.phase_end,
        'freqkhz': tag.freqkhz,
        'device_name': tag.device_name,
        'timestamp': time.strftime("%H:%M:%S")
    }
    
    print(f"[DEBUG] Real-time tag detected: {tag_data}")
    print(f"[DEBUG] WebSocket clients connected: {len(socketio.server.manager.rooms)}")
    
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
        
        # Determine mode type like C# code
        mode_type = 1  # Default R2000
        if reader_type_val in [0x62, 0x61, 0x64, 0x66, 0x65, 0x67, 0x68]:  # C6
            mode_type = 0
        elif reader_type_val in [0x71, 0x31, 0x70, 0x72, 0x5F, 0x7F, 0x76, 0x56, 0x38,
                                0x57, 0x77, 0x39, 0x55, 0x75, 0x35, 0x33, 0x53, 0x73,
                                0x3A, 0x5A, 0x7A, 0x3B, 0x5B, 0x7B, 0x3C, 0x5C, 0x7C,
                                0x3D, 0x5D, 0x7D, 0x3E, 0x5E, 0x7E, 0x40, 0x41, 0x42,
                                0x6A, 0x6B, 0x6C]:  # RRUx180
            mode_type = 2
        elif reader_type_val == 0x11:  # 9810
            mode_type = 3
        elif reader_type_val in [0x91, 0x92, 0x93, 0x94]:  # FD
            mode_type = 4
        
        # Determine antenna count like C# code
        antenna_count = 4  # Default
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
            'antenna_check_status': 'Enabled' if check_ant[0] == 1 else 'Disabled'
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
        # Lấy session từ param1 (giống C# GetSession)
        cfg_num = 0x09  # Configuration number for Param1
        cfg_data = bytearray(256)
        data_len = [0]
        result_param = reader.get_cfg_parameter(cfg_num, cfg_data, data_len)
        if result_param == 0 and data_len[0] >= 2:
            session_val = cfg_data[1] if cfg_data[1] < 4 else 0
        else:
            session_val = 0  # fallback nếu lỗi
        
        # First, call select_cmd for each antenna (like C# code)
        sel_action_val = 0     # int = 0 (like C# code: Session, 0, MaskMem, ...)
        mask_mem_val = 1       # int = EPC memory (like C# MaskMem = 1)
        mask_addr_bytes = bytes([0, 0])  # 2 bytes address (like C# MaskAdr = new byte[2])
        mask_len_val = 0       # int = no mask (like C# MaskLen = 0)
        mask_data_bytes = bytes(100)  # 100 bytes array (like C# MaskData = new byte[100])
        truncate_val = 0       # int = no truncate (like C# code: ..., 0, frmcomportindex)
        select_antenna = 0xFFFF  # SelectAntenna = 0xFFFF (all antennas) like C# code

        # Call select_cmd for each antenna (4 antennas like C# code)
        # Following C# code exactly: for (int m = 0; m < 4; m++)
        for antenna in range(4): 
            result = reader.select_cmd(
                antenna=select_antenna,  # SelectAntenna = 0xFFFF (all antennas)
                session=session_val,
                sel_action=sel_action_val,
                mask_mem=mask_mem_val,
                mask_addr=mask_addr_bytes,
                mask_len=mask_len_val,
                mask_data=mask_data_bytes,
                truncate=truncate_val,
                antenna_num=1
            )
            print(f"[DEBUG] Antenna {antenna} result: {result} session: {session_val}")
            time.sleep(0.005)  # 5ms delay like C# Thread.Sleep(5)
        
        # Clear any existing data (like C# code clears dataGridView5, epclist, etc.)
        # This is handled by the frontend when starting new inventory
        
        # Now start inventory with target
        print(f"[DEBUG] Starting Fast Mode inventory with target: {target}")
        result = reader.start_inventory(target)
        print(f"[DEBUG] Fast Mode inventory start result: {result}")
        
        if result == 0:
            print(f"[DEBUG] Fast Mode inventory started successfully")
            return jsonify({'success': True, 'message': f'Inventory đã bắt đầu (Target {"A" if target == 0 else "B"})'})
        elif result == 51:
            return jsonify({'success': False, 'message': 'Inventory is already running'}), 400
        else:
            return jsonify({'success': False, 'message': f'Không thể bắt đầu inventory (code: {result})'}), 400
            
    except Exception as e:
        logger.error(f"Start inventory error: {e}")
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500

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
    'RF_Profile': 0,
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
        if mode_type == 'mix':
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
        # Get ModeType from reader info
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
            # Determine ModeType from reader type (exact C# logic)
            reader_type_val = reader_type[0]
            mode_type_val = 1  # Default R2000
            if reader_type_val in [0x62, 0x61, 0x64, 0x66, 0x65, 0x67, 0x68]:  # C6
                mode_type_val = 0
            elif reader_type_val in [0x71, 0x31, 0x70, 0x72, 0x5F, 0x7F, 0x76, 0x56, 0x38,
                                0x57, 0x77, 0x39, 0x55, 0x75, 0x35, 0x33, 0x53, 0x73,
                                0x3A, 0x5A, 0x7A, 0x3B, 0x5B, 0x7B, 0x3C, 0x5C, 0x7C,
                                0x3D, 0x5D, 0x7D, 0x3E, 0x5E, 0x7E, 0x40, 0x41, 0x42,
                                0x6A, 0x6B, 0x6C]:  # RRUx180
                mode_type_val = 2
            elif reader_type_val == 0x11:  # 9810
                mode_type_val = 3
            elif reader_type_val in [0x91, 0x92, 0x93, 0x94]:  # FD
                mode_type_val = 4
            
            if mode_type_val == 2:
                g2_inventory_vars['Profile'] = g2_inventory_vars['RF_Profile'] | 0xC0
                result = reader.set_profile(profile=g2_inventory_vars['Profile'])
                if result != 0:
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
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500

def preset_target(read_mode, select_antenna):
    """Exact C# PresetTarget implementation"""
    global g2_inventory_vars
    
    cur_session = 0
    if read_mode > 0:
        mask_mem = 1
        mask_addr = bytearray(2)
        mask_len = 0
        mask_data = bytearray(100)
        
        # Get ModeType from reader info
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
            reader_type_val = reader_type[0]
            mode_type_val = 1  # Default R2000
            if reader_type_val in [0x62, 0x61, 0x64, 0x66, 0x65, 0x67, 0x68]:  # C6
                mode_type_val = 0
            elif reader_type_val in [0x71, 0x31, 0x70, 0x72, 0x5F, 0x7F, 0x76, 0x56, 0x38,
                                0x57, 0x77, 0x39, 0x55, 0x75, 0x35, 0x33, 0x53, 0x73,
                                0x3A, 0x5A, 0x7A, 0x3B, 0x5B, 0x7B, 0x3C, 0x5C, 0x7C,
                                0x3D, 0x5D, 0x7D, 0x3E, 0x5E, 0x7E, 0x40, 0x41, 0x42,
                                0x6A, 0x6B, 0x6C]:  # RRUx180
                mode_type_val = 2
            elif reader_type_val == 0x11:  # 9810
                mode_type_val = 3
            elif reader_type_val in [0x91, 0x92, 0x93, 0x94]:  # FD
                mode_type_val = 4
            
            # Determine AntennaNum from reader type
            antenna_num = 1  # Default
            if reader_type_val in [0x11, 0x8A, 0x8B, 0x0C, 0x20, 0x62, 0x67, 0x73, 0x53, 
                              0x75, 0x55, 0x7B, 0x5B, 0x3B, 0x35, 0x33, 0x92, 0x40]:
                antenna_num = 4
            elif reader_type_val in [0x27, 0x65, 0x77, 0x57, 0x39, 0x94, 0x42]:
                antenna_num = 16
            elif reader_type_val in [0x26, 0x68, 0x76, 0x56, 0x38, 0x93, 0x41]:
                antenna_num = 8
            
            if (read_mode == 254 or read_mode == 253) and (mode_type_val == 2):
                if g2_inventory_vars['Session'] == 254:
                    g2_inventory_vars['Session'] = 253
                    cur_session = 2
                else:
                    g2_inventory_vars['Session'] = 254
                    cur_session = 3
                
                if read_mode == 253:
                    g2_inventory_vars['Profile'] = 0xC1
                else:
                    g2_inventory_vars['Profile'] = 0xC5
                result = reader.set_profile(profile=g2_inventory_vars['Profile'])
                if result != 0:
                    logger.warning(f"Set profile failed with code {result}, continuing without profile setting")
                
            elif read_mode == 255:
                cur_session = 2
                g2_inventory_vars['Session'] = read_mode
                for m in range(2):
                    reader.select_cmd(
                        antenna=select_antenna, session=cur_session, sel_action=0,
                        mask_mem=mask_mem, mask_addr=bytes(mask_addr), mask_len=mask_len,
                        mask_data=bytes(mask_data), truncate=0, antenna_num=antenna_num
                    )
                    time.sleep(0.005)  # Thread.Sleep(5)
                cur_session = 3
                for m in range(2):
                    reader.select_cmd(
                        antenna=select_antenna, session=cur_session, sel_action=0,
                        mask_mem=mask_mem, mask_addr=bytes(mask_addr), mask_len=mask_len,
                        mask_data=bytes(mask_data), truncate=0, antenna_num=antenna_num
                    )
                    time.sleep(0.005)  # Thread.Sleep(5)
                    
            elif read_mode < 4:
                cur_session = read_mode
                g2_inventory_vars['Session'] = cur_session
                for m in range(4):
                    reader.select_cmd(
                        antenna=select_antenna, session=cur_session, sel_action=0,
                        mask_mem=mask_mem, mask_addr=bytes(mask_addr), mask_len=mask_len,
                        mask_data=bytes(mask_data), truncate=0, antenna_num=antenna_num
                    )
                    time.sleep(0.005)  # Thread.Sleep(5)
        else:
            g2_inventory_vars['Session'] = read_mode

def inventory_worker():
    """Exact C# inventory() method implementation"""
    global g2_inventory_vars, detected_tags
    
    g2_inventory_vars['fIsInventoryScan'] = True
    
    while not g2_inventory_vars['toStopThread']:
        try:
            if g2_inventory_vars['Session'] == 255:
                # Auto session mode (exact C# logic)
                g2_inventory_vars['FastFlag'] = 0
                if g2_inventory_vars.get('mode_type') == 'mix':
                    flash_mix_g2()
                else:
                    flash_g2()
            else:
                # Manual session mode (exact C# logic)
                # Determine AntennaNum from reader type
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
                    reader_type_val = reader_type[0]
                    antenna_num = 1  # Default
                    if reader_type_val in [0x11, 0x8A, 0x8B, 0x0C, 0x20, 0x62, 0x67, 0x73, 0x53, 
                                          0x75, 0x55, 0x7B, 0x5B, 0x3B, 0x35, 0x33, 0x92, 0x40]:
                        antenna_num = 4
                    elif reader_type_val in [0x27, 0x65, 0x77, 0x57, 0x39, 0x94, 0x42]:
                        antenna_num = 16
                    elif reader_type_val in [0x26, 0x68, 0x76, 0x56, 0x38, 0x93, 0x41]:
                        antenna_num = 8
                    
                    # Cycle through antennas (exact C# logic)
                    for m in range(antenna_num):
                        if g2_inventory_vars['toStopThread']:
                            break
                            
                        g2_inventory_vars['InAnt'] = m | 0x80
                        g2_inventory_vars['FastFlag'] = 1
                        
                        if g2_inventory_vars['antlist'][m] == 1:
                            # Handle session 2 and 3 target switching (exact C# logic)
                            if (g2_inventory_vars['Session'] > 1 and g2_inventory_vars['Session'] < 4 and 
                                g2_inventory_vars.get('enable_target_times', True)):  # s2,s3 with target times enabled
                                if g2_inventory_vars['AA_times'] + 1 > g2_inventory_vars['targettimes']:
                                    g2_inventory_vars['Target'] = 1 - g2_inventory_vars['Target']  # A/B state switch
                                    g2_inventory_vars['AA_times'] = 0
                            
                            # Call appropriate inventory function based on mode
                            if g2_inventory_vars.get('mode_type') == 'mix':
                                flash_mix_g2()
                            else:
                                flash_g2()
                                preset_profile()
            
            # Small delay between cycles (exact C# Thread.Sleep(5))
            time.sleep(0.005)
            
        except Exception as ex:
            logger.error(f"Inventory error: {ex}")
            # Continue running despite errors (exact C# behavior)
            time.sleep(0.1)
    
    # Cleanup when thread stops (exact C# logic)
    # Get ModeType from reader info
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
        reader_type_val = reader_type[0]
        mode_type_val = 1  # Default R2000
        if reader_type_val in [0x62, 0x61, 0x64, 0x66, 0x65, 0x67, 0x68]:  # C6
            mode_type_val = 0
        elif reader_type_val in [0x71, 0x31, 0x70, 0x72, 0x5F, 0x7F, 0x76, 0x56, 0x38,
                            0x57, 0x77, 0x39, 0x55, 0x75, 0x35, 0x33, 0x53, 0x73,
                            0x3A, 0x5A, 0x7A, 0x3B, 0x5B, 0x7B, 0x3C, 0x5C, 0x7C,
                            0x3D, 0x5D, 0x7D, 0x3E, 0x5E, 0x7E, 0x40, 0x41, 0x42,
                            0x6A, 0x6B, 0x6C]:  # RRUx180
            mode_type_val = 2
        elif reader_type_val == 0x11:  # 9810
            mode_type_val = 3
        elif reader_type_val in [0x91, 0x92, 0x93, 0x94]:  # FD
            mode_type_val = 4
        
        if mode_type_val == 2:
            g2_inventory_vars['Profile'] = g2_inventory_vars['RF_Profile'] | 0xC0
            result = reader.set_profile(profile=g2_inventory_vars['Profile'])
            if result != 0:
                logger.warning(f"Failed to restore profile: {result}")
    
    # Final cleanup (exact C# logic)
    g2_inventory_vars['fIsInventoryScan'] = False
    g2_inventory_vars['mythread'] = None

def flash_g2():
    """Exact C# flash_G2() method implementation"""
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
    g2_inventory_vars['tagrate'] = 0
    g2_inventory_vars['NewCardNum'] = 0
    
    # Debug logging to verify all parameters are being passed correctly
    logger.info(f"[DEBUG] flash_g2() parameters:")
    logger.info(f"  Q_value: {g2_inventory_vars['Qvalue']}")
    logger.info(f"  Session: {g2_inventory_vars['Session']}")
    logger.info(f"  Scan_time: {g2_inventory_vars['Scantime']} (={g2_inventory_vars['Scantime']*100}ms)")
    logger.info(f"  Target: {g2_inventory_vars['Target']}")
    logger.info(f"  In_ant: {g2_inventory_vars['InAnt']} (0x{g2_inventory_vars['InAnt']:02X})")
    logger.info(f"  TID_flag: {g2_inventory_vars['TIDFlag']}")
    logger.info(f"  TID_addr: {g2_inventory_vars['tidAddr']} (0x{g2_inventory_vars['tidAddr']:02X})")
    logger.info(f"  TID_len: {g2_inventory_vars['tidLen']}")
    logger.info(f"  Mode_type: {g2_inventory_vars.get('mode_type', 'unknown')}")
    
    # Call inventory_g2 (exact C# RWDev.Inventory_G2 call)
    # Pass all parameters including TID parameters that were set in api_start_inventory_g2
    tags = reader.inventory_g2(
        q_value=g2_inventory_vars['Qvalue'],
        session=g2_inventory_vars['Session'],
        scan_time=g2_inventory_vars['Scantime'],
        target=g2_inventory_vars['Target'],
        in_ant=g2_inventory_vars['InAnt'],
        tid_flag=g2_inventory_vars['TIDFlag'],
        tid_addr=g2_inventory_vars['tidAddr'],
        tid_len=g2_inventory_vars['tidLen']
    )
    
    # C# style error handling - check if tags is a list (success) or error code
    if isinstance(tags, list):
        result = 0  # Success
        g2_inventory_vars['CardNum'] = len(tags)
        
        # Process detected tags
        for tag in tags:
            tag_data = {
                'epc': tag.epc,
                'rssi': tag.rssi,
                'antenna': tag.antenna,
                'timestamp': time.strftime("%H:%M:%S"),
                'phase_begin': getattr(tag, 'phase_begin', 0),
                'phase_end': getattr(tag, 'phase_end', 0),
                'freqkhz': getattr(tag, 'freqkhz', 0)
            }
            # Emit to WebSocket immediately (C# style real-time updates)
            socketio.emit('tag_detected', tag_data)
            detected_tags.append(tag_data)
            g2_inventory_vars['total_tagnum'] += 1
    else:
        # tags is actually an error code
        result = tags
        error_desc = get_return_code_desc(result)
        logger.error(f"Inventory G2 failed: {error_desc} (code: {result})")
        g2_inventory_vars['CardNum'] = 0
    
    cmd_time = int(time.time() * 1000) - cbtime
    
    # Handle result codes (exact C# logic)
    if result not in [0x01, 0x02, 0xF8, 0xF9, 0xEE, 0xFF]:
        # Handle connection issues (exact C# logic)
        logger.warning(f"Non-standard inventory result: {result}")
    
    if result == 0x30:
        g2_inventory_vars['CardNum'] = 0
    
    if g2_inventory_vars['CardNum'] == 0:
        if g2_inventory_vars['Session'] > 1 and g2_inventory_vars.get('enable_target_times', True):
            g2_inventory_vars['AA_times'] += 1
    else:
        # Get ModeType from reader info
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
            reader_type_val = reader_type[0]
            mode_type_val = 1  # Default R2000
            if reader_type_val in [0x62, 0x61, 0x64, 0x66, 0x65, 0x67, 0x68]:  # C6
                mode_type_val = 0
            elif reader_type_val in [0x71, 0x31, 0x70, 0x72, 0x5F, 0x7F, 0x76, 0x56, 0x38,
                                0x57, 0x77, 0x39, 0x55, 0x75, 0x35, 0x33, 0x53, 0x73,
                                0x3A, 0x5A, 0x7A, 0x3B, 0x5B, 0x7B, 0x3C, 0x5C, 0x7C,
                                0x3D, 0x5D, 0x7D, 0x3E, 0x5E, 0x7E, 0x40, 0x41, 0x42,
                                0x6A, 0x6B, 0x6C]:  # RRUx180
                mode_type_val = 2
            elif reader_type_val == 0x11:  # 9810
                mode_type_val = 3
            elif reader_type_val in [0x91, 0x92, 0x93, 0x94]:  # FD
                mode_type_val = 4
            
            if (mode_type_val == 2) and (g2_inventory_vars['readMode'] == 253 or g2_inventory_vars['readMode'] == 254) and (g2_inventory_vars['NewCardNum'] == 0):
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
        if g2_inventory_vars['Session'] > 1 and g2_inventory_vars.get('enable_target_times', True):
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
    global g2_inventory_vars
    
    # Get ModeType from reader info
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
        reader_type_val = reader_type[0]
        mode_type_val = 1  # Default R2000
        if reader_type_val in [0x62, 0x61, 0x64, 0x66, 0x65, 0x67, 0x68]:  # C6
            mode_type_val = 0
        elif reader_type_val in [0x71, 0x31, 0x70, 0x72, 0x5F, 0x7F, 0x76, 0x56, 0x38,
                            0x57, 0x77, 0x39, 0x55, 0x75, 0x35, 0x33, 0x53, 0x73,
                            0x3A, 0x5A, 0x7A, 0x3B, 0x5B, 0x7B, 0x3C, 0x5C, 0x7C,
                            0x3D, 0x5D, 0x7D, 0x3E, 0x5E, 0x7E, 0x40, 0x41, 0x42,
                            0x6A, 0x6B, 0x6C]:  # RRUx180
            mode_type_val = 2
        elif reader_type_val == 0x11:  # 9810
            mode_type_val = 3
        elif reader_type_val in [0x91, 0x92, 0x93, 0x94]:  # FD
            mode_type_val = 4
        
        if (g2_inventory_vars['readMode'] == 254 or g2_inventory_vars['readMode'] == 253) and (mode_type_val == 2):
            if (g2_inventory_vars['Profile'] == 0x01) and (g2_inventory_vars['readMode'] == 253):
                if g2_inventory_vars['tagrate'] < 150 or g2_inventory_vars['CardNum'] < 150:
                    g2_inventory_vars['Profile'] = 0xC5
                    result = reader.set_profile(profile=g2_inventory_vars['Profile'])
                    if result != 0:
                        logger.warning(f"Preset profile set failed with code {result}")
            elif g2_inventory_vars['Profile'] == 0x05:
                if g2_inventory_vars['NewCardNum'] < 5:
                    g2_inventory_vars['Profile'] = 0xCD
                    result = reader.set_profile(profile=g2_inventory_vars['Profile'])
                    if result != 0:
                        logger.warning(f"Preset profile set failed with code {result}")
                    g2_inventory_vars['AA_times'] = 0
            elif g2_inventory_vars['Profile'] == 0x0D:
                if g2_inventory_vars['NewCardNum'] > 20:
                    g2_inventory_vars['Profile'] = 0xC5
                    result = reader.set_profile(profile=g2_inventory_vars['Profile'])
                    if result != 0:
                        logger.warning(f"Preset profile set failed with code {result}")
                elif g2_inventory_vars['AA_times'] >= g2_inventory_vars['targettimes']:
                    if g2_inventory_vars['readMode'] == 254:
                        g2_inventory_vars['Profile'] = 0xC5
                    elif g2_inventory_vars['readMode'] == 253:
                        g2_inventory_vars['Profile'] = 0xC1
                    result = reader.set_profile(profile=g2_inventory_vars['Profile'])
                    if result != 0:
                        logger.warning(f"Preset profile set failed with code {result}")
                    g2_inventory_vars['AA_times'] = 0
                    g2_inventory_vars['Target'] = 1 - g2_inventory_vars['Target']  # A/B state switch

@app.route('/api/stop_inventory', methods=['POST'])
def api_stop_inventory():
    """API dừng inventory"""
    try:
        result = reader.stop_inventory()
        if result == 0:
            logger.info("Tags inventory stopped successfully")
            return {"success": True, "message": "Đã dừng tags inventory thành công"}
        else:
            logger.error(f"Không thể dừng tags inventory (code: {result})")
            return {"success": False, "message": f'Không thể dừng tags inventory (code: {result})'}
    except Exception as e:
        logger.error(f"Stop tags inventory error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}

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
        return jsonify({'success': True, 'message': f'Đã thiết lập công suất: {power} dBm'})
    else:
        return jsonify({'success': False, 'message': f'Không thể thiết lập công suất (code: {result})'})

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
        return {"success": False, "message": f"Lỗi: {str(e)}"}

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
        return {"success": False, "message": f"Lỗi: {str(e)}"}

@socketio.on('connect')
def handle_connect():
    """Xử lý khi client kết nối WebSocket"""
    logger.info(f"🔌 WebSocket client connected: {request.sid}")
    print(f"[DEBUG] WebSocket client connected: {request.sid}")
    socketio.emit('status', {'message': 'Connected to server'})
    connected_clients.add(request.sid)
    print(f"[DEBUG] Total connected clients: {len(connected_clients)}")

@socketio.on('disconnect')
def handle_disconnect():
    """Xử lý khi client ngắt kết nối WebSocket"""
    logger.info(f"🔌 WebSocket client disconnected: {request.sid}")
    print(f"[DEBUG] WebSocket client disconnected: {request.sid}")
    connected_clients.remove(request.sid)
    print(f"[DEBUG] Total connected clients: {len(connected_clients)}")

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
            return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
        
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
            return jsonify({"success": False, "message": f"Set failed with error code: {result}"})
            
    except Exception as e:
        logger.error(f"Set Param1 error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/get_param1', methods=['GET'])
def api_get_param1():
    """API lấy parameter 1 (Q-value, Session, Phase) - cfgNum = 0x09"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
        
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
            return jsonify({"success": False, "message": f"Get failed with error code: {result}"})
            
    except Exception as e:
        logger.error(f"Get Param1 error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/set_tid_param', methods=['POST'])
def api_set_tid_param():
    """API thiết lập TID parameter - cfgNum = 0x0A"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
        
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
            return jsonify({"success": False, "message": f"Set failed with error code: {result}"})
            
    except Exception as e:
        logger.error(f"Set TID Param error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/get_tid_param', methods=['GET'])
def api_get_tid_param():
    """API lấy TID parameter - cfgNum = 0x0A"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
        
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
            return jsonify({"success": False, "message": f"Get failed with error code: {result}"})
            
    except Exception as e:
        logger.error(f"Get TID Param error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/set_mask_param', methods=['POST'])
def api_set_mask_param():
    """API thiết lập Mask parameter - cfgNum = 0x0B"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
        
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
            return jsonify({"success": False, "message": f"Set failed with error code: {result}"})
            
    except Exception as e:
        logger.error(f"Set Mask Param error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/get_mask_param', methods=['GET'])
def api_get_mask_param():
    """API lấy Mask parameter - cfgNum = 0x0B"""
    try:
        if not reader.is_connected:
            return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
        
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
            return jsonify({"success": False, "message": f"Get failed with error code: {result}"})
            
    except Exception as e:
        logger.error(f"Get Mask Param error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

if __name__ == '__main__':
    logger.info(f"Starting RFID Web Control Panel on {config.HOST}:{config.PORT}")
    socketio.run(app, debug=config.DEBUG, host=config.HOST, port=config.PORT) 