#!/usr/bin/env python3
"""
Continuous monitoring example for UHF RFID Reader Python SDK
"""

import sys
import time
import signal
import platform
from pathlib import Path
from collections import defaultdict

# Add the parent directory to the path so we can import the SDK
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PythonSDK import UHFReader, RFIDTag

class ContinuousMonitor:
    """Class for continuous RFID tag monitoring"""
    
    def __init__(self):
        self.reader = UHFReader()
        self.running = False
        self.tag_counts = defaultdict(int)
        self.last_seen = {}
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\nReceived signal {signum}, shutting down...")
        self.stop()
    
    def tag_callback(self, tag: RFIDTag):
        """Callback function called when tags are detected"""
        current_time = time.time()
        
        # Update tag count and last seen time
        self.tag_counts[tag.uid] += 1
        self.last_seen[tag.uid] = current_time
        
        # Print tag information
        timestamp = time.strftime('%H:%M:%S', time.localtime(current_time))
        print(f"[{timestamp}] Tag: {tag.uid}")
        print(f"         Antenna: {tag.ant}")
        print(f"         RSSI: {tag.rssi}")
        print(f"         Count: {self.tag_counts[tag.uid]}")
        print(f"         Device: {tag.device_name}")
        print("-" * 40)
    
    def start(self, port=None, baud: int = 5):
        """Start continuous monitoring"""
        print("UHF RFID Reader - Continuous Monitoring")
        print("=" * 50)
        print(f"Platform: {platform.system()}")
        print("Press Ctrl+C to stop monitoring")
        print()
        
        # Get available ports
        available_ports = self.reader.get_available_ports()
        print(f"Available ports: {available_ports}")
        
        if not available_ports:
            print("No serial ports available!")
            return False
        
        # Determine port to use
        if port is None:
            if platform.system() == "Windows":
                port = 1  # COM1
                print(f"Windows detected - using COM{port}")
            else:
                # On macOS/Linux, show available ports and use the first one
                print("macOS/Linux detected - available ports:")
                for i, p in enumerate(available_ports, 1):
                    print(f"  {i}. {p}")
                port = 1  # First available port
                print(f"Using port index {port} ({available_ports[port-1]})")
        else:
            print(f"Using specified port: {port}")
        
        # Try to connect
        print(f"Connecting to port: {port}")
        result = self.reader.open_com_port(port=port, com_addr=255, baud=baud)
        
        if result != 0:
            print(f"Connection failed with error code: {result}")
            if platform.system() != "Windows":
                print(f"\nPlatform-specific troubleshooting:")
                print(f"  - Available ports: {available_ports}")
                print(f"  - Try using a specific device path:")
                if available_ports:
                    print(f"    reader.open_com_port('{available_ports[0]}', 255, {baud})")
                print(f"  - Check device permissions: ls -l /dev/tty*")
            return False
        
        print("✓ Connected successfully!")
        
        try:
            # Get reader information
            info = self.reader.get_reader_information()
            print(f"Reader: {info.get('version_info', 'Unknown')}")
            print(f"Power: {info.get('power_dbm', 'Unknown')} dBm")
            
            # Set RF power if needed
            current_power = info.get('power_dbm', 0)
            if current_power < 25:
                print("Setting RF power to 30 dBm...")
                self.reader.set_rf_power(30)
            
            # Set up callback
            self.reader.init_rfid_callback(self.tag_callback)
            
            # Start continuous inventory
            print("\nStarting continuous monitoring...")
            print("Waiting for tags...")
            print("-" * 40)
            
            result = self.reader.start_inventory()
            if result != 0:
                print(f"Failed to start inventory: {result}")
                return False
            
            self.running = True
            
            # Main monitoring loop
            start_time = time.time()
            while self.running:
                time.sleep(1)
                
                # Print statistics every 30 seconds
                elapsed = time.time() - start_time
                if elapsed > 0 and int(elapsed) % 30 == 0:
                    self.print_statistics()
            
            return True
            
        except Exception as e:
            print(f"Error during monitoring: {e}")
            return False
        
        finally:
            self.stop()
    
    def stop(self):
        """Stop monitoring"""
        if self.running:
            print("\nStopping monitoring...")
            self.reader.stop_inventory()
            self.reader.close_com_port()
            self.running = False
            print("✓ Monitoring stopped")
    
    def print_statistics(self):
        """Print monitoring statistics"""
        if not self.tag_counts:
            return
        
        print("\n" + "=" * 50)
        print("MONITORING STATISTICS")
        print("=" * 50)
        
        total_detections = sum(self.tag_counts.values())
        unique_tags = len(self.tag_counts)
        
        print(f"Total detections: {total_detections}")
        print(f"Unique tags: {unique_tags}")
        print()
        
        # Show most frequently detected tags
        print("Most active tags:")
        sorted_tags = sorted(self.tag_counts.items(), key=lambda x: x[1], reverse=True)
        
        for i, (tag_uid, count) in enumerate(sorted_tags[:5], 1):
            last_time = self.last_seen.get(tag_uid, 0)
            if last_time > 0:
                time_ago = time.time() - last_time
                if time_ago < 60:
                    last_seen_str = f"{int(time_ago)}s ago"
                elif time_ago < 3600:
                    last_seen_str = f"{int(time_ago/60)}m ago"
                else:
                    last_seen_str = f"{int(time_ago/3600)}h ago"
            else:
                last_seen_str = "Unknown"
            
            print(f"  {i}. {tag_uid[:16]}... (detected {count} times, last: {last_seen_str})")
        
        print("=" * 50)

def main():
    """Main function"""
    monitor = ContinuousMonitor()
    
    try:
        # Start monitoring with default port detection
        success = monitor.start(baud=5)
        
        if not success:
            print("Failed to start monitoring")
            return 1
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 