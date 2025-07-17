"""
Custom exceptions for the UHF RFID Reader SDK
"""

class UHFReaderError(Exception):
    """Base exception for UHF Reader operations"""
    pass

class ConnectionError(UHFReaderError):
    """Raised when connection to the reader fails"""
    pass

class TimeoutError(UHFReaderError):
    """Raised when operations timeout"""
    pass

class InvalidParameterError(UHFReaderError):
    """Raised when invalid parameters are provided"""
    pass

class ReaderNotConnectedError(UHFReaderError):
    """Raised when trying to perform operations on a disconnected reader"""
    pass

class OperationInProgressError(UHFReaderError):
    """Raised when trying to perform operations while scanning is in progress"""
    pass 