from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
import threading
import time
import json
from typing import Optional, Dict, List
import serial
import logging
from uhf_reader import UHFReader

# Import các hàm từ zk.py
from zk import (
    get_reader_info, 
    get_profile, 
    set_profile,
)

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

class RFIDWebController:
    def __init__(self):
        self.reader = None
        self.is_connected = False
        self.current_profile = None
        self.antenna_power = {}
        
    def get_reader_info(self) -> Dict:
        """Lấy thông tin reader"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        try:
            info = get_reader_info(self.reader)
            if info:
                return {"success": True, "data": info}
            else:
                return {"success": False, "message": "Không thể lấy thông tin reader"}
        except Exception as e:
            logger.error(f"Get reader info error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def get_current_profile(self) -> Dict:
        """Lấy profile hiện tại"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        try:
            profile = get_profile(self.reader)
            if profile is not None:
                self.current_profile = profile
                return {"success": True, "data": {"profile": profile}}
            else:
                return {"success": False, "message": "Không thể lấy profile"}
        except Exception as e:
            logger.error(f"Get profile error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def set_profile(self, profile_num: int, save_on_power_down: bool = True) -> Dict:
        """Thiết lập profile"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        if profile_num not in config.PROFILE_CONFIGS:
            return {"success": False, "message": "Profile không hợp lệ"}
        
        try:
            result = set_profile(self.reader, profile_num, save_on_power_down)
            if result:
                self.current_profile = profile_num
                logger.info(f"Set profile to {profile_num}")
                return {"success": True, "message": f"Đã thiết lập profile: {profile_num}"}
            else:
                return {"success": False, "message": "Không thể thiết lập profile"}
        except Exception as e:
            logger.error(f"Set profile error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}

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
    """API lấy thông tin reader"""
    result = reader.get_reader_information()
    return jsonify({'success': True, 'data': result})

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
    """API bắt đầu inventory G2 mode"""
    data = request.get_json()
    mode_type = data.get('mode_type', 'epc')
    
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
        
        # Now start inventory with G2 mode type
        # For G2 mode, we need to set the appropriate mode before starting inventory
        # This would typically involve setting configuration parameters based on mode_type
        # For now, we'll use the same start_inventory but with different target based on mode
        
        target = 0  # Default target A for G2 mode
        if mode_type == 'tid':
            # TID mode specific configuration could go here
            pass
        elif mode_type == 'mix':
            # Mix mode specific configuration could go here
            pass
        elif mode_type == 'fastid':
            # FastID mode specific configuration could go here
            pass
        # EPC is default
        
        result = reader.start_inventory(target)
        
        if result == 0:
            return jsonify({'success': True, 'message': f'G2 Mode inventory đã bắt đầu ({mode_type.upper()})'})
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
            "is_connected": rfid_controller.is_connected,
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