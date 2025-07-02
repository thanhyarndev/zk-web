"""
RFID Tag data structure
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class RFIDTag:
    """
    Represents an RFID tag with its properties
    
    Attributes:
        packet_param: Packet parameter
        length: Length of the tag data
        uid: Unique identifier of the tag
        phase_begin: Beginning phase
        phase_end: Ending phase
        rssi: Received Signal Strength Indicator
        freq_khz: Frequency in kHz
        ant: Antenna number
        device_name: Name of the device that detected the tag
    """
    packet_param: int = 0
    length: int = 0
    uid: str = ""
    phase_begin: int = 0
    phase_end: int = 0
    rssi: int = 0
    freq_khz: int = 0
    ant: int = 0
    device_name: str = ""
    
    def __str__(self) -> str:
        return f"RFIDTag(UID={self.uid}, RSSI={self.rssi}, Ant={self.ant}, Freq={self.freq_khz}kHz)"
    
    def __repr__(self) -> str:
        return self.__str__() 