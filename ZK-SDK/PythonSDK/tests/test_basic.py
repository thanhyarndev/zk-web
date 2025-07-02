"""
Basic tests for UHF RFID Reader Python SDK
"""

import unittest
import sys
from pathlib import Path

# Add the parent directory to the path so we can import the SDK
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PythonSDK import UHFReader, RFIDTag
from PythonSDK.exceptions import UHFReaderError, ReaderNotConnectedError

class TestUHFReader(unittest.TestCase):
    """Test cases for UHFReader class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.reader = UHFReader()
    
    def tearDown(self):
        """Clean up after tests"""
        if self.reader.is_connected:
            self.reader.close_com_port()
    
    def test_reader_initialization(self):
        """Test reader initialization"""
        self.assertIsNotNone(self.reader)
        self.assertFalse(self.reader.is_connected)
        self.assertFalse(self.reader.is_scanning)
        self.assertEqual(self.reader.com_addr, 255)
    
    def test_get_available_ports(self):
        """Test getting available ports"""
        ports = self.reader.get_available_ports()
        self.assertIsInstance(ports, list)
        # Ports should be strings
        for port in ports:
            self.assertIsInstance(port, str)
    
    def test_hex_conversion(self):
        """Test hex string conversion methods"""
        test_data = b"Hello World"
        hex_str = self.reader.bytes_to_hex_string(test_data)
        converted_data = self.reader.hex_string_to_bytes(hex_str)
        self.assertEqual(test_data, converted_data)
    
    def test_crc_check(self):
        """Test CRC checking"""
        # Test with valid CRC
        valid_data = "BB0003000100047E"
        self.assertTrue(self.reader.check_crc(valid_data))
        
        # Test with invalid data
        invalid_data = "BB000300010004"
        self.assertFalse(self.reader.check_crc(invalid_data))
    
    def test_reader_not_connected_operations(self):
        """Test operations when reader is not connected"""
        # These operations should raise ReaderNotConnectedError
        with self.assertRaises(ReaderNotConnectedError):
            self.reader.get_reader_information()
        
        with self.assertRaises(ReaderNotConnectedError):
            self.reader.set_rf_power(30)
        
        with self.assertRaises(ReaderNotConnectedError):
            self.reader.inventory_g2()
        
        with self.assertRaises(ReaderNotConnectedError):
            self.reader.read_data_g2("1234567890ABCDEF")
    
    def test_invalid_parameters(self):
        """Test invalid parameter handling"""
        # Test with invalid EPC
        with self.assertRaises(ValueError):
            self.reader.hex_string_to_bytes("invalid hex")
        
        # Test with empty hex string
        with self.assertRaises(ValueError):
            self.reader.hex_string_to_bytes("")

class TestRFIDTag(unittest.TestCase):
    """Test cases for RFIDTag class"""
    
    def test_tag_creation(self):
        """Test RFIDTag creation"""
        tag = RFIDTag()
        self.assertIsNotNone(tag)
        self.assertEqual(tag.uid, "")
        self.assertEqual(tag.ant, 0)
        self.assertEqual(tag.rssi, 0)
    
    def test_tag_with_data(self):
        """Test RFIDTag with data"""
        tag = RFIDTag(
            uid="E200341201B8020110B8A8",
            ant=1,
            rssi=-45,
            device_name="COM1"
        )
        
        self.assertEqual(tag.uid, "E200341201B8020110B8A8")
        self.assertEqual(tag.ant, 1)
        self.assertEqual(tag.rssi, -45)
        self.assertEqual(tag.device_name, "COM1")
    
    def test_tag_string_representation(self):
        """Test tag string representation"""
        tag = RFIDTag(
            uid="E200341201B8020110B8A8",
            ant=1,
            rssi=-45,
            freq_khz=915000
        )
        
        str_repr = str(tag)
        self.assertIn("E200341201B8020110B8A8", str_repr)
        self.assertIn("1", str_repr)
        self.assertIn("-45", str_repr)
        self.assertIn("915000", str_repr)

class TestExceptions(unittest.TestCase):
    """Test cases for custom exceptions"""
    
    def test_uhf_reader_error(self):
        """Test UHFReaderError"""
        error = UHFReaderError("Test error")
        self.assertEqual(str(error), "Test error")
    
    def test_reader_not_connected_error(self):
        """Test ReaderNotConnectedError"""
        error = ReaderNotConnectedError("Reader not connected")
        self.assertEqual(str(error), "Reader not connected")
        self.assertIsInstance(error, UHFReaderError)

if __name__ == "__main__":
    unittest.main() 