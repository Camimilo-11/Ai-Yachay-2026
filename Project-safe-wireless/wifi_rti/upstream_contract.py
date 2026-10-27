"""WiFiMeasurement de IsukaW (MIT), revisión 91aee04; sin cambios de campos."""
from dataclasses import dataclass

@dataclass
class WiFiMeasurement:
    """Data class for a single WiFi measurement."""
    timestamp: float
    ssid: str
    bssid: str  # MAC address of access point
    signal_strength: float  # RSSI in dBm
    frequency: float  # MHz
    channel: int
    interface: str

