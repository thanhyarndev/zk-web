#!/usr/bin/env python3
"""
Real-time G2 Inventory Debug Monitor

This script monitors the g2_inventory_debug.log file and displays
the logs in real-time with color coding and filtering options.
"""

import os
import sys
import time
import argparse
from datetime import datetime

# Color codes for terminal output
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'

def colorize(text, color):
    """Add color to text"""
    return f"{color}{text}{Colors.RESET}"

def parse_log_line(line):
    """Parse a log line and extract components"""
    try:
        # Expected format: timestamp | g2_inventory_debug | level | funcName | message
        parts = line.strip().split(' | ')
        if len(parts) >= 5:
            timestamp = parts[0]
            logger_name = parts[1]
            level = parts[2]
            func_name = parts[3]
            message = ' | '.join(parts[4:])
            return {
                'timestamp': timestamp,
                'logger': logger_name,
                'level': level,
                'function': func_name,
                'message': message
            }
    except Exception as e:
        pass
    return None

def get_level_color(level):
    """Get color for log level"""
    level_colors = {
        'DEBUG': Colors.CYAN,
        'INFO': Colors.GREEN,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED
    }
    return level_colors.get(level, Colors.WHITE)

def get_function_color(function):
    """Get color for function name"""
    function_colors = {
        'preset_target': Colors.MAGENTA,
        'inventory_worker': Colors.BLUE,
        'preset_profile': Colors.YELLOW,
        'flash_g2': Colors.GREEN,
        'flash_mix_g2': Colors.CYAN
    }
    return function_colors.get(function, Colors.WHITE)

def filter_logs(log_data, filters):
    """Filter logs based on criteria"""
    if not filters:
        return True
    
    # Filter by function
    if filters.get('function') and filters['function'].lower() not in log_data['function'].lower():
        return False
    
    # Filter by level
    if filters.get('level') and filters['level'].upper() != log_data['level']:
        return False
    
    # Filter by message content
    if filters.get('message') and filters['message'].lower() not in log_data['message'].lower():
        return False
    
    return True

def monitor_logs(log_file, filters=None, follow=True):
    """Monitor log file in real-time"""
    print(f"{Colors.BOLD}🔍 G2 Inventory Debug Monitor{Colors.RESET}")
    print(f"📁 Monitoring: {log_file}")
    print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Filters: {filters if filters else 'None'}")
    print("-" * 80)
    
    # Check if log file exists
    if not os.path.exists(log_file):
        print(f"{Colors.RED}❌ Log file not found: {log_file}{Colors.RESET}")
        print(f"💡 Make sure the Flask app is running and has generated logs.")
        return
    
    # Get initial file size
    file_size = os.path.getsize(log_file)
    file_position = file_size
    
    try:
        while True:
            # Check if file has grown
            current_size = os.path.getsize(log_file)
            
            if current_size > file_position:
                with open(log_file, 'r') as f:
                    f.seek(file_position)
                    new_lines = f.readlines()
                    
                    for line in new_lines:
                        log_data = parse_log_line(line)
                        if log_data and filter_logs(log_data, filters):
                            # Format the output
                            timestamp = colorize(log_data['timestamp'], Colors.WHITE)
                            level = colorize(log_data['level'], get_level_color(log_data['level']))
                            function = colorize(log_data['function'], get_function_color(log_data['function']))
                            message = log_data['message']
                            
                            # Highlight important patterns
                            if 'FUNCTION START' in message:
                                message = colorize(message, Colors.BOLD + Colors.GREEN)
                            elif 'FUNCTION END' in message:
                                message = colorize(message, Colors.BOLD + Colors.RED)
                            elif 'CYCLE' in message:
                                message = colorize(message, Colors.BOLD + Colors.BLUE)
                            elif 'ERROR' in message or 'FAILED' in message:
                                message = colorize(message, Colors.RED)
                            elif 'SUCCESS' in message or 'SUCCESSFUL' in message:
                                message = colorize(message, Colors.GREEN)
                            
                            print(f"{timestamp} | {level} | {function} | {message}")
                
                file_position = current_size
            
            if not follow:
                break
                
            time.sleep(0.1)  # Check every 100ms
            
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}🛑 Monitoring stopped by user{Colors.RESET}")

def main():
    parser = argparse.ArgumentParser(description='Monitor G2 Inventory Debug Logs')
    parser.add_argument('--log-file', default='g2_inventory_debug.log', 
                       help='Path to the log file (default: g2_inventory_debug.log)')
    parser.add_argument('--function', '-f', 
                       help='Filter by function name (e.g., preset_target, inventory_worker)')
    parser.add_argument('--level', '-l', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Filter by log level')
    parser.add_argument('--message', '-m', 
                       help='Filter by message content')
    parser.add_argument('--no-follow', action='store_true',
                       help='Don\'t follow the log file (just read existing content)')
    
    args = parser.parse_args()
    
    # Build filters
    filters = {}
    if args.function:
        filters['function'] = args.function
    if args.level:
        filters['level'] = args.level
    if args.message:
        filters['message'] = args.message
    
    # Start monitoring
    monitor_logs(args.log_file, filters, follow=not args.no_follow)

if __name__ == '__main__':
    main() 