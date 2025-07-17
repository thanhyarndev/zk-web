"""
RFID Tag data structure
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class RFIDTag:
    """
    Represents an RFID tag with its properties - matches C# RFIDTag class
    
    Attributes:
        epc: EPC (Electronic Product Code) as hex string
        antenna: Antenna number that detected the tag
        rssi: Received Signal Strength Indicator
        packet_param: Packet parameter from response
        len: Length of the tag data
        phase_begin: Beginning phase (for InventoryMix_G2)
        phase_end: Ending phase (for InventoryMix_G2)
        freqkhz: Frequency in kHz (for InventoryMix_G2)
        device_name: Name of the device that detected the tag
    """
    epc: str = ""
    antenna: int = 0
    rssi: int = 0
    packet_param: int = 0
    len: int = 0
    phase_begin: int = 0
    phase_end: int = 0
    freqkhz: int = 0
    device_name: str = ""
    
    def __str__(self) -> str:
        return f"RFIDTag(EPC={self.epc}, RSSI={self.rssi}, Ant={self.antenna}, Freq={self.freqkhz}kHz)"
    
    def __repr__(self) -> str:
        return self.__str__() 