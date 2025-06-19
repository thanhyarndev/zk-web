# RFID Reader Web Control Panel

Ứng dụng web để điều khiển RFID Reader Ex10 Series thay thế cho giao diện terminal.

## Tính năng

- 🌐 **Giao diện web hiện đại**: Thay thế hoàn toàn giao diện terminal
- 🔌 **Kết nối serial**: Hỗ trợ kết nối qua serial port
- 📊 **Real-time monitoring**: Hiển thị tags và thống kê theo thời gian thực
- ⚙️ **Cấu hình đầy đủ**: Điều khiển power, antenna, profile, buzzer
- 📱 **Responsive design**: Tương thích với mobile và desktop
- 🔄 **WebSocket**: Cập nhật dữ liệu real-time qua WebSocket

## Cài đặt

1. **Clone repository**:
```bash
git clone <repository-url>
cd zk-web-app
```

2. **Cài đặt dependencies**:
```bash
pip install -r requirements.txt
```

3. **Chạy ứng dụng**:
```bash
python app.py
```

4. **Truy cập web**:
Mở trình duyệt và truy cập: `http://localhost:5000`

## Sử dụng

### 1. Kết nối Reader
- Nhập serial port (mặc định: `/dev/cu.usbserial-10`)
- Chọn baudrate (mặc định: 57600)
- Nhấn "Kết nối"

### 2. Inventory Control
- **Start Inventory (Target A)**: Bắt đầu quét tags với target A
- **Start Inventory (Target B)**: Bắt đầu quét tags với target B  
- **Stop Inventory**: Dừng quét tags
- **Real-time stats**: Hiển thị tốc độ đọc và tổng số tags

### 3. Cấu hình
- **RF Power**: Điều chỉnh công suất RF (0-30 dBm)
- **Antenna Control**: Bật/tắt từng antenna
- **Profile Management**: Chọn profile phù hợp
- **Buzzer Control**: Bật/tắt buzzer

### 4. Monitoring
- **Tags Display**: Hiển thị danh sách tags đã phát hiện
- **Real-time Updates**: Cập nhật thông tin tags theo thời gian thực
- **Statistics**: Thống kê tốc độ đọc và tổng số tags

## API Endpoints

### Connection
- `POST /api/connect` - Kết nối reader
- `POST /api/disconnect` - Ngắt kết nối reader

### Reader Info
- `GET /api/reader_info` - Lấy thông tin reader
- `GET /api/get_profile` - Lấy profile hiện tại
- `GET /api/get_antenna_power` - Lấy công suất antennas

### Inventory Control
- `POST /api/start_inventory` - Bắt đầu inventory
- `POST /api/stop_inventory` - Dừng inventory
- `GET /api/get_tags` - Lấy danh sách tags

### Configuration
- `POST /api/set_power` - Thiết lập công suất RF
- `POST /api/set_buzzer` - Thiết lập buzzer
- `POST /api/set_profile` - Thiết lập profile
- `POST /api/enable_antennas` - Bật antennas
- `POST /api/disable_antennas` - Tắt antennas

## WebSocket Events

- `tag_detected` - Khi phát hiện tag mới
- `stats_update` - Cập nhật thống kê
- `status` - Trạng thái kết nối

## Cấu trúc Project

```
zk-web-app/
├── app.py              # Flask application
├── zk.py               # RFID SDK (original)
├── requirements.txt    # Python dependencies
├── README.md          # Documentation
└── templates/
    └── index.html     # Web interface
```

## Troubleshooting

### Lỗi kết nối serial
- Kiểm tra serial port có đúng không
- Đảm bảo reader đã được kết nối
- Kiểm tra quyền truy cập serial port

### Lỗi WebSocket
- Kiểm tra firewall
- Đảm bảo port 5000 không bị block

### Performance Issues
- Giảm tần suất cập nhật nếu có quá nhiều tags
- Tối ưu hóa network connection

## Contributing

1. Fork repository
2. Tạo feature branch
3. Commit changes
4. Push to branch
5. Tạo Pull Request

## License

MIT License - xem file LICENSE để biết thêm chi tiết.

## Support

Nếu gặp vấn đề, vui lòng tạo issue trên GitHub repository. 