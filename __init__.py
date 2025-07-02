"""
UHF RFID Reader Python SDK

A Python implementation of the UHF RFID Reader SDK, providing
functionality for communicating with UHF RFID readers via
serial (COM) and network (TCP) connections.

This SDK supports:
- Serial and TCP connections
- Tag inventory operations
- Read/Write operations on tags
- Reader configuration
- Real-time tag detection with callbacks
"""

from .uhf_reader import UHFReader
from .rfid_tag import RFIDTag
from .reader import Reader
from .exceptions import UHFReaderError, ConnectionError, TimeoutError

__version__ = "1.0.0"
__author__ = "Huy Le @ Nextwaves Industries"

__all__ = [
    'UHFReader',
    'RFIDTag', 
    'Reader',
    'UHFReaderError',
    'ConnectionError',
    'TimeoutError'
] 