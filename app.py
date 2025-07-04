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

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# Khởi tạo controller
reader = UHFReader()

def tag_callback(tag):
    import time
    tag_data = tag.__dict__ if hasattr(tag, '__dict__') else dict(tag)
    tag_data['timestamp'] = time.strftime("%H:%M:%S")
    print(f"[DEBUG] Emitting tag_detected: {tag_data}")
    socketio.emit('tag_detected', tag_data)
    detected_tags.append(tag_data)
    inventory_stats['total_count'] = inventory_stats.get('total_count', 0) + 1

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
        return jsonify({'success': False, 'error': f'Connection failed with code: {result}'}), 400

@app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    """API ngắt kết nối reader"""
    result = reader.close_com_port()
    # Emit connection status to all connected clients
    socketio.emit('connection_status', {'connected': False, 'message': 'Disconnected successfully'})
    return jsonify({'success': True, 'message': 'Disconnected successfully'})

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
            return jsonify({'success': False, 'error': f'Get Reader Information failed: {result}'}), 400
        
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
        result = reader.start_inventory(target)
        
        if result == 0:
            return jsonify({'success': True, 'message': f'Inventory đã bắt đầu (Target {"A" if target == 0 else "B"})'})
        elif result == 51:
            return jsonify({'success': False, 'message': 'Inventory is already running'}), 400
        else:
            return jsonify({'success': False, 'message': f'Không thể bắt đầu inventory (code: {result})'}), 400
            
    except Exception as e:
        logger.error(f"Start inventory error: {e}")
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500

@app.route('/api/start_inventory_g2', methods=['POST'])
def api_start_inventory_g2():
    """API bắt đầu inventory G2 mode - based on C# btIventoryG2_Click"""
    data = request.get_json()
    
    try:
        # Extract parameters from request
        mode_type = data.get('mode_type', 'epc')  # epc, tid, mix, fastid
        scan_time = data.get('scan_time', 0)  # com_scantime.SelectedIndex
        q_value = data.get('q_value', 4)  # com_Q.SelectedIndex
        session = data.get('session', 0)  # com_S.SelectedIndex
        target = data.get('target', 0)  # com_Target.SelectedIndex
        target_times = data.get('target_times', 1)  # text_target.Text
        enable_phase = data.get('enable_phase', False)  # check_phase.Checked
        enable_rate = data.get('enable_rate', False)  # checkBox_rate.Checked
        antennas = data.get('antennas', [1])  # Selected antennas
        
        # Mix mode specific parameters
        mix_mem = data.get('mix_mem', 0)  # com_MixMem.SelectedIndex
        read_addr = data.get('read_addr', '0000')  # text_readadr.Text
        read_len = data.get('read_len', '04')  # text_readLen.Text
        psd = data.get('psd', '00000000')  # text_readpsd.Text
        
        # Validate mix mode parameters
        if mode_type == 'mix':
            if len(read_addr) != 4 or len(read_len) != 2 or len(psd) != 8:
                return jsonify({'success': False, 'message': 'Mix inventory parameter error!!!'}), 400
        
        # Clear existing data (equivalent to C# clearing lists and UI)
        global detected_tags, inventory_stats
        detected_tags.clear()
        inventory_stats = {
            'total_tags': 0,
            'total_time': 0,
            'commands_sent': 0,
            'commands_successful': 0
        }
        
        # Set scan time
        scan_time_byte = scan_time
        
        # Set Q value with rate flag if enabled
        q_value_byte = q_value
        if enable_rate:
            q_value_byte |= 0x80
        
        
        # Set profile for ModeType 2 (if applicable) - matching C# logic
        # TODO: Determine ModeType value from UI or configuration
        # if ModeType == 2:
        #     rf_profile = 0  # RF_Profile is initialized as 0 in C#
        #     profile_with_flags = rf_profile | 0xC0  # 0 | 0xC0 = 0xC0
        #     result = reader.set_profile(profile=profile_with_flags)
        #     if result != 0:
        #         logger.warning(f"Failed to set profile: {result}")
        #     else:
        #         logger.info(f"Profile set successfully with flags: {profile_with_flags}")
        
        # Set read mode based on session
        read_mode = 0
        if session == 4:
            read_mode = 255
        elif session < 4:
            read_mode = session
        elif session == 5:
            read_mode = 254
        elif session == 6:
            read_mode = 253
        
        # Set scan type and flags based on mode
        tid_flag = 0
        scan_type = 0
        tid_addr = 0
        tid_len = 0
        
        if mode_type == 'epc':
            tid_flag = 0
            scan_type = 0
        elif mode_type == 'tid':
            tid_flag = 1
            tid_addr = int(read_addr, 16) & 0x00FF
            tid_len = int(read_len, 16)
            scan_type = 1
        elif mode_type == 'fastid':
            tid_flag = 0
            q_value_byte |= 0x20
            scan_type = 2
        elif mode_type == 'mix':
            scan_type = 3
            # TODO: Implement mix mode specific logic
            # ReadMem = (byte)com_MixMem.SelectedIndex
            # ReadAdr = HexStringToByteArray(text_readadr.Text)
            # ReadLen = Convert.ToByte(text_readLen.Text, 16)
            # Psd = HexStringToByteArray(text_readpsd.Text)
        
        # Add phase flag if enabled
        if enable_phase:
            q_value_byte |= 0x10
        
        # Build antenna configuration
        select_antenna = 0
        ant_list = [0] * 16
        
        for ant_num in antennas:
            if 1 <= ant_num <= 16:
                ant_list[ant_num - 1] = 1
                select_antenna |= (1 << (ant_num - 1))
        
        # TODO: Implement PresetTarget function
        # PresetTarget(readMode, SelectAntenna)
        
        # Set target
        target_byte = target
        
        # TODO: Implement inventory thread logic
        # This would replace the C# mythread = new Thread(new ThreadStart(inventory))
        # For now, we'll use the existing start_inventory method with modified parameters
        
        # Start inventory with calculated parameters
        result = reader.start_inventory_g2(
            target=target_byte,
            scan_time=scan_time_byte,
            q_value=q_value_byte,
            session=session,
            read_mode=read_mode,
            scan_type=scan_type,
            tid_flag=tid_flag,
            tid_addr=tid_addr,
            tid_len=tid_len,
            select_antenna=select_antenna,
            mode_type=mode_type
        )
        
        if result == 0:
            return jsonify({
                'success': True, 
                'message': f'G2 Mode inventory started successfully ({mode_type.upper()})',
                'parameters': {
                    'mode_type': mode_type,
                    'scan_type': scan_type,
                    'q_value': q_value_byte,
                    'session': session,
                    'target': target_byte,
                    'antennas': antennas,
                    'scan_time': scan_time_byte
                }
            })
        elif result == 51:
            return jsonify({'success': False, 'message': 'Inventory is already running'}), 400
        else:
            return jsonify({'success': False, 'message': f'Không thể bắt đầu G2 inventory (code: {result})'}), 400
            
    except Exception as e:
        logger.error(f"Start G2 inventory error: {e}")
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500

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

@app.route('/api/stop_tags_inventory', methods=['POST'])
def api_stop_tags_inventory():
    """API dừng tags inventory"""
    global stop_inventory_flag
    
    try:
        # Set flag để dừng inventory
        stop_inventory_flag = True
        
        # Đợi thread kết thúc
        if inventory_thread and inventory_thread.is_alive():
            print(f"[DEBUG] Waiting for tags inventory thread to finish...")
            inventory_thread.join(timeout=1.0)  # Đợi tối đa 3 giây
        
        print(f"Tags inventory stopped successfully")
        return {"[DEBUG] success": True, "message": "Đã dừng tags inventory thành công"}
    except Exception as e:
        print(f"[DEBUG] Stop tags inventory error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}

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

@app.route('/api/set_buzzer', methods=['POST'])
def api_set_buzzer():
    """API thiết lập buzzer"""
    data = request.get_json()
    enable = data.get('enable', True)
    
    result = rfid_controller.set_buzzer(enable)
    return jsonify(result)

@app.route('/api/get_profile', methods=['GET'])
def api_get_profile():
    """API lấy profile hiện tại"""
    result = rfid_controller.get_current_profile()
    return jsonify(result)

@app.route('/api/set_profile', methods=['POST'])
def api_set_profile():
    """API thiết lập profile"""
    data = request.get_json()
    profile_num = data.get('profile_num', 1)
    save_on_power_down = data.get('save_on_power_down', True)
    
    result = rfid_controller.set_profile(profile_num, save_on_power_down)
    return jsonify(result)

@app.route('/api/enable_antennas', methods=['POST'])
def api_enable_antennas():
    """API bật antennas"""
    data = request.get_json()
    antennas = data.get('antennas', [1])
    save_on_power_down = data.get('save_on_power_down', True)
    
    result = rfid_controller.enable_antennas(antennas, save_on_power_down)
    return jsonify(result)

@app.route('/api/disable_antennas', methods=['POST'])
def api_disable_antennas():
    """API tắt antennas"""
    data = request.get_json()
    antennas = data.get('antennas', [1])
    save_on_power_down = data.get('save_on_power_down', True)
    
    result = rfid_controller.disable_antennas(antennas, save_on_power_down)
    return jsonify(result)

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

@app.route('/api/config', methods=['GET'])
def api_get_config():
    """API lấy cấu hình"""
    try:
        config_data = {
            "default_port": config.DEFAULT_PORT,
            "default_baudrate": config.DEFAULT_BAUDRATE,
            "max_power": config.MAX_POWER,
            "min_power": config.MIN_POWER,
            "max_antennas": config.MAX_ANTENNAS,
            "profiles": config.PROFILE_CONFIGS,
            "max_tags_display": config.MAX_TAGS_DISPLAY
        }
        return {"success": True, "data": config_data}
    except Exception as e:
        logger.error(f"Config API error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}

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
    socketio.emit('status', {'message': 'Connected to server'})
    connected_clients.add(request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Xử lý khi client ngắt kết nối WebSocket"""
    logger.info(f"🔌 WebSocket client disconnected: {request.sid}")
    connected_clients.remove(request.sid)

@socketio.on('message')
def handle_message(message):
    """Xử lý message từ client"""
    logger.info(f"📨 Received WebSocket message: {message}")

@app.route('/api/tags_inventory', methods=['POST'])
def api_tags_inventory():
    """API thực hiện một lượt inventory với cấu hình tuỳ chọn (không liên tục)"""
    try:
        data = request.get_json()
        q_value = int(data.get("q_value", 4))
        session = int(data.get("session", 0))
        antenna = int(data.get("antenna", 1))
        scan_time = int(data.get("scan_time", 10))

        # Call inventory_g2 for a single scan
        tags = reader.inventory_g2(q_value=q_value, session=session, scan_time=scan_time, in_ant=antenna)
        
        # Convert tags to list of dictionaries
        tag_list = []
        for tag in tags:
            tag_list.append({
                "epc": tag.epc,
                "rssi": tag.rssi,
                "antenna": tag.antenna,
                "timestamp": time.strftime("%H:%M:%S")
            })
        
        return jsonify({
            "success": True,
            "message": f"Found {len(tag_list)} tags",
            "data": tag_list
        })
    except Exception as e:
        logger.error(f"Tags inventory error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

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