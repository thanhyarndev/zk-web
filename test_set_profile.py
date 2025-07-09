#!/usr/bin/env python3
"""
Simple test script for set_profile function
Tests the C# SetProfile(ref byte ComAdr, ref byte Profile) compatibility
"""

import time
import sys
import os

# Add current directory to path to import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from uhf_reader import UHFReader
from config import get_config

def test_set_profile():
    """Test set_profile function with various profile values"""
    
    print("=== Set Profile Test ===")
    print("Testing C# SetProfile(ref byte ComAdr, ref byte Profile) compatibility")
    print()
    
    # Load configuration
    config = get_config()
    
    # Create reader instance
    reader = UHFReader()
    
    # Test profile values (matching C# values from app.py)
    test_profiles = [
        0x01,  # Profile 1
        0x05,  # Profile 5  
        0x0D,  # Profile 13
        0xC1,  # Profile 193 (RRUx180 special)
        0xC5,  # Profile 197 (RRUx180 special)
        0xCD,  # Profile 205 (RRUx180 special)
    ]
    
    print("Test profiles to try:")
    for profile in test_profiles:
        print(f"  - 0x{profile:02X} ({profile})")
    print()
    
    # Try to connect to reader
    print("Attempting to connect to reader...")
    try:
        result = reader.open_com_port(port=config.DEFAULT_PORT, com_addr=255, baud=config.DEFAULT_BAUDRATE)
        if result != 0:
            print(f"❌ Connection failed with code: {result}")
            print("Please make sure:")
            print("  1. Reader is connected to the specified port")
            print("  2. Port is not in use by another application")
            print("  3. Reader is powered on")
            return False
        
        print("✅ Connected successfully!")
        print(f"   Port: {config.DEFAULT_PORT}")
        print(f"   Baudrate: {config.DEFAULT_BAUDRATE}")
        print(f"   Com Address: {reader.com_addr}")
        print()
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False
    
    # Test each profile value
    print("Testing set_profile with different values:")
    print("-" * 60)
    
    for profile in test_profiles:
        print(f"Testing profile: 0x{profile:02X} ({profile})")
        
        try:
            # Create bytearrays for C# ref parameter simulation
            com_addr_bytearray = bytearray([reader.com_addr])
            profile_bytearray = bytearray([profile])
            
            print(f"  Before: com_addr=0x{com_addr_bytearray[0]:02X}, profile=0x{profile_bytearray[0]:02X}")
            
            # Call set_profile (exact C# SetProfile behavior)
            result, new_profile = reader.set_profile(com_addr=com_addr_bytearray[0], profile=profile_bytearray[0])
            
            print(f"  Result: {result}")
            if result == 0:
                print(f"  ✅ Success! New profile: 0x{new_profile:02X}")
                print(f"     com_addr: 0x{com_addr_bytearray[0]:02X} (was 0x{reader.com_addr:02X})")
                print(f"     profile: 0x{profile_bytearray[0]:02X} (was 0x{profile:02X})")
                if com_addr_bytearray[0] != reader.com_addr:
                    reader.com_addr = com_addr_bytearray[0]
                    print(f"     Updated reader.com_addr to: 0x{reader.com_addr:02X}")
            else:
                print(f"  ❌ Failed with error code: {result}")
                if result == 49:
                    print("     (CRC error - possible communication issue)")
                elif result == 48:
                    print("     (Timeout - no response from reader)")
                else:
                    print("     (Other error)")
            print()
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            print()
    
    # Test with invalid profile values (should fail gracefully)
    print("Testing with invalid profile values:")
    print("-" * 60)
    
    invalid_profiles = [256, 300, 1000]  # Values > 255 (invalid byte range)
    
    for profile in invalid_profiles:
        print(f"Testing invalid profile: {profile} (0x{profile:02X})")
        
        try:
            com_addr_bytearray = bytearray([reader.com_addr])
            profile_bytearray = bytearray([profile & 0xFF])  # Force to byte range
            
            print(f"  Before: com_addr=0x{com_addr_bytearray[0]:02X}, profile=0x{profile_bytearray[0]:02X}")
            
            result = reader.set_profile(com_addr=com_addr_bytearray, profile=profile_bytearray)
            
            print(f"  Result: {result}")
            if result == 0:
                print(f"  ✅ Success with truncated value: 0x{profile_bytearray[0]:02X}")
            else:
                print(f"  ❌ Failed with error code: {result}")
            print()
            
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            print()
    
    # Cleanup
    print("Cleaning up...")
    try:
        reader.close_com_port()
        print("✅ Disconnected successfully")
    except Exception as e:
        print(f"⚠️  Disconnect warning: {e}")
    
    print()
    print("=== Test Complete ===")
    return True

def test_uhf_reader_set_profile():
    """Test the UHFReader.set_profile wrapper function"""
    
    print("=== UHFReader.set_profile Test ===")
    print("Testing the high-level set_profile wrapper")
    print()
    
    # Load configuration
    config = get_config()
    
    # Create reader instance
    reader = UHFReader()
    
    # Try to connect
    print("Attempting to connect to reader...")
    try:
        result = reader.open_com_port(port=config.DEFAULT_PORT, com_addr=255, baud=config.DEFAULT_BAUDRATE)
        if result != 0:
            print(f"❌ Connection failed with code: {result}")
            return False
        
        print("✅ Connected successfully!")
        print()
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False
    
    # Test the wrapper function
    test_profiles = [0x01, 0x05, 0x0D, 0xC1, 0xC5, 0xCD]
    
    print("Testing UHFReader.set_profile wrapper:")
    print("-" * 60)
    
    for profile in test_profiles:
        print(f"Testing profile: 0x{profile:02X} ({profile})")
        
        try:
            # Store original com_addr
            original_com_addr = reader.com_addr
            
            # Call the wrapper function
            result, new_profile = reader.set_profile(profile=profile)
            
            print(f"  Result: {result}")
            
            # According to SDK: only 0 means success
            if result == 0:
                print(f"  ✅ Success! Profile set to: 0x{new_profile:02X}")
            elif result >= 0 and result <= 255:
                print(f"  ❌ Failed with error code: {result}")
                if result == 1:
                    print("     (Parameter error)")
                elif result == 5:
                    print("     (Command not supported)")
                elif result == 13:
                    print("     (Invalid parameter)")
                else:
                    print("     (Other error)")
            else:
                print(f"  ❌ Failed with error code: {result}")
            
            # Check if com_addr changed
            if reader.com_addr != original_com_addr:
                print(f"  📝 Com address updated: 0x{original_com_addr:02X} → 0x{reader.com_addr:02X}")
            
            print()
            
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            print()
    
    # Cleanup
    print("Cleaning up...")
    try:
        reader.close_com_port()
        print("✅ Disconnected successfully")
    except Exception as e:
        print(f"⚠️  Disconnect warning: {e}")
    
    print()
    print("=== UHFReader Test Complete ===")
    return True

def test_raw_response():
    """Test to see the raw response from set_profile"""
    
    print("=== Raw Response Test ===")
    print("Testing to see the actual response data from set_profile")
    print()
    
    # Load configuration
    config = get_config()
    
    # Create reader instance
    reader = UHFReader()
    
    # Try to connect
    print("Attempting to connect to reader...")
    try:
        result = reader.open_com_port(port=config.DEFAULT_PORT, com_addr=255, baud=config.DEFAULT_BAUDRATE)
        if result != 0:
            print(f"❌ Connection failed with code: {result}")
            return False
        
        print("✅ Connected successfully!")
        print()
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False
    
    # Test with a simple profile
    test_profile = 0x01
    
    print(f"Testing raw response with profile: 0x{test_profile:02X}")
    print("-" * 60)
    
    try:
        # Store original com_addr
        original_com_addr = reader.com_addr
        
        # Call the wrapper function
        result = reader.set_profile(profile=test_profile)
        
        print(f"Result: {result}")
        
        # Try to access the raw response data if possible
        if hasattr(reader, 'uhf') and hasattr(reader.uhf, 'recv_buffer') and hasattr(reader.uhf, 'recv_length'):
            print(f"Raw response buffer: {reader.uhf.recv_buffer[:reader.uhf.recv_length].hex()}")
            print(f"Response length: {reader.uhf.recv_length}")
            if reader.uhf.recv_length >= 6:
                print(f"Response frame analysis:")
                print(f"  Len: 0x{reader.uhf.recv_buffer[0]:02X}")
                print(f"  Adr: 0x{reader.uhf.recv_buffer[1]:02X}")
                print(f"  reCmd: 0x{reader.uhf.recv_buffer[2]:02X}")
                print(f"  Status: 0x{reader.uhf.recv_buffer[3]:02X}")
                if reader.uhf.recv_length >= 5:
                    print(f"  Data: 0x{reader.uhf.recv_buffer[4]:02X}")
                if reader.uhf.recv_length >= 7:
                    print(f"  CRC: 0x{reader.uhf.recv_buffer[5]:02X}{reader.uhf.recv_buffer[6]:02X}")
        
        print()
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        print()
    
    # Cleanup
    print("Cleaning up...")
    try:
        reader.close_com_port()
        print("✅ Disconnected successfully")
    except Exception as e:
        print(f"⚠️  Disconnect warning: {e}")
    
    print()
    print("=== Raw Response Test Complete ===")
    return True

if __name__ == "__main__":
    print("Set Profile Test Script")
    print("=" * 50)
    print()
    
    # Test 1: Direct low-level set_profile
    print("TEST 1: Direct low-level set_profile function")
    print("=" * 50)
    test_set_profile()
    
    print()
    print()
    
    # Test 2: UHFReader wrapper
    print("TEST 2: UHFReader.set_profile wrapper function")
    print("=" * 50)
    test_uhf_reader_set_profile()
    
    print()
    print()
    
    # Test 3: Raw response analysis
    print("TEST 3: Raw response analysis")
    print("=" * 50)
    test_raw_response()
    
    print()
    print("All tests completed!") 