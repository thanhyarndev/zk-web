# G2 Inventory Debug System

This debugging system provides comprehensive logging for the G2 inventory mode functions to help you understand the execution flow and troubleshoot issues.

## Overview

The debug system tracks three main functions:

1. **`preset_target`** - Session management and target selection (MAGENTA color)
2. **`inventory_worker`** - Main inventory loop and antenna cycling (BLUE color)
3. **`preset_profile`** - Profile optimization for RRUx180 readers (YELLOW color)
4. **`flash_g2`** - Individual inventory calls (GREEN color)

## Setup

### 1. Start the Flask Application

```bash
python app.py
```

The application will automatically create a `g2_inventory_debug.log` file when G2 inventory operations are performed.

### 2. Monitor Debug Logs

Use the debug monitor script to view logs in real-time:

```bash
# Monitor all logs
python debug_monitor.py

# Monitor only preset_target function
python debug_monitor.py --function preset_target

# Monitor only inventory_worker function
python debug_monitor.py --function inventory_worker

# Monitor only preset_profile function
python debug_monitor.py --function preset_profile

# Monitor only flash_g2 function
python debug_monitor.py --function flash_g2

# Monitor only ERROR level logs
python debug_monitor.py --level ERROR

# Monitor logs containing "FUNCTION START"
python debug_monitor.py --message "FUNCTION START"

# Monitor logs containing "CYCLE"
python debug_monitor.py --message "CYCLE"
```

## Color Coding

- **MAGENTA**: `preset_target` function
- **BLUE**: `inventory_worker` function
- **YELLOW**: `preset_profile` function
- **GREEN**: `flash_g2` function
- **CYAN**: DEBUG level messages
- **GREEN**: INFO level messages
- **YELLOW**: WARNING level messages
- **RED**: ERROR level messages

## Key Debug Information

### Function Start/End Markers

Each function logs clear start and end markers:

```
=== FUNCTION START ===
=== FUNCTION END ===
```

### Cycle Tracking

The `inventory_worker` function tracks each cycle:

```
=== CYCLE 1 START ===
=== CYCLE 1 END ===
```

### Parameter Tracking

All functions log their input parameters and state changes:

- Session values
- Target states (A/B switching)
- Antenna configurations
- Profile changes
- Error codes and results

### Target Switching Logic

The system tracks A/B target switching:

```
Target switched | old_target=0, new_target=1
```

### Profile Optimization

For RRUx180 readers, profile changes are logged:

```
Profile changed from 0x01 to 0xC5
```

## Debug Scenarios

### 1. Understanding Session Management

Filter for session-related logs:

```bash
python debug_monitor.py --message "session"
```

### 2. Tracking Target Switching

Filter for target switching:

```bash
python debug_monitor.py --message "target"
```

### 3. Monitoring Antenna Cycling

Filter for antenna processing:

```bash
python debug_monitor.py --message "antenna"
```

### 4. Profile Optimization

Filter for profile changes:

```bash
python debug_monitor.py --message "profile"
```

### 5. Error Tracking

Monitor only errors:

```bash
python debug_monitor.py --level ERROR
```

## Example Debug Session

1. **Start the Flask app** in one terminal:

   ```bash
   python app.py
   ```

2. **Start the debug monitor** in another terminal:

   ```bash
   python debug_monitor.py --function inventory_worker
   ```

3. **Start G2 inventory** from the web interface

4. **Watch the real-time logs** to see:
   - Function entry/exit points
   - Parameter values
   - Antenna cycling
   - Target switching
   - Profile changes
   - Error conditions

## Troubleshooting

### Common Issues

1. **No logs appearing**: Make sure G2 inventory is actually running
2. **Log file not found**: Check that the Flask app has started and generated logs
3. **Function not showing**: Verify the function name in the filter

### Debug Tips

1. **Start with broad monitoring**: `python debug_monitor.py`
2. **Narrow down with filters**: Add function or level filters
3. **Look for patterns**: Function start/end, cycle numbers, error codes
4. **Check timing**: Look at timestamps to understand execution flow

## Log File Location

The debug logs are written to: `g2_inventory_debug.log`

You can also view the raw log file directly:

```bash
tail -f g2_inventory_debug.log
```

## Integration with Web Interface

The debug system works alongside the web interface. You can:

1. Start the Flask app
2. Open the web interface in your browser
3. Start G2 inventory from the web interface
4. Monitor the debug logs in real-time in another terminal

This gives you both the user interface for control and detailed debugging information for troubleshooting.
