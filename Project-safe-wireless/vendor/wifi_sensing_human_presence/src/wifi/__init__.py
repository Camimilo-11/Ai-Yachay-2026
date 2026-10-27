"""
WiFi sensing module for human presence detection.

This module provides WiFi signal monitoring and feature extraction for detecting
human presence and movement using RSSI and CSI measurements.
"""

import time
import os
import numpy as np
import pandas as pd
import subprocess
import threading
import queue
import re
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from loguru import logger
from collections import defaultdict, deque
import psutil
import netifaces


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


@dataclass
class CSIMeasurement:
    """Data class for CSI (Channel State Information) measurement."""
    timestamp: float
    subcarrier_index: int
    amplitude: complex
    phase: float
    magnitude: float
    rssi: float
    interface: str


class WiFiScanner:
    """WiFi scanner for RSSI measurements using system tools."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize WiFi scanner.
        
        Args:
            config: WiFi configuration dictionary
        """
        self.config = config
        self.interface = config.get("interface", self._get_default_interface())
        self.scan_interval = config.get("scan_interval", 1.0)
        self.target_ssids = config.get("target_ssids", [])
        
        self.is_scanning = False
        self.measurement_queue = queue.Queue(maxsize=1000)
        self.scan_thread = None
        
        # Measurement history for feature extraction
        self.measurement_history = defaultdict(lambda: deque(maxlen=100))
        
        logger.info(f"WiFi scanner initialized on interface: {self.interface}")
    
    def _get_default_interface(self) -> str:
        """Get the default WiFi interface name."""
        interfaces = netifaces.interfaces()
        
        # Common WiFi interface names
        wifi_patterns = ['wlan', 'wifi', 'en0', 'wlp']
        
        for interface in interfaces:
            for pattern in wifi_patterns:
                if pattern in interface.lower():
                    return interface
        
        # Fallback to first interface that's not loopback
        for interface in interfaces:
            if interface != 'lo':
                return interface
        
        return 'wlan0'  # Default fallback
    
    def start_scanning(self) -> bool:
        """Start WiFi scanning in background thread."""
        try:
            self.is_scanning = True
            self.scan_thread = threading.Thread(target=self._scan_loop)
            self.scan_thread.daemon = True
            self.scan_thread.start()
            
            logger.info("WiFi scanning started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start WiFi scanning: {e}")
            return False
    
    def stop_scanning(self):
        """Stop WiFi scanning."""
        self.is_scanning = False
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=2)
        logger.info("WiFi scanning stopped")
    
    def _scan_loop(self):
        """Main scanning loop."""
        while self.is_scanning:
            try:
                measurements = self._perform_scan()
                
                for measurement in measurements:
                    # Filter by target SSIDs if specified
                    if not self.target_ssids or measurement.ssid in self.target_ssids:
                        if not self.measurement_queue.full():
                            self.measurement_queue.put(measurement)
                        
                        # Add to history for feature extraction
                        key = f"{measurement.ssid}_{measurement.bssid}"
                        self.measurement_history[key].append(measurement)
                
                time.sleep(self.scan_interval)
                
            except Exception as e:
                logger.error(f"Error in scan loop: {e}")
                time.sleep(1)
    
    def _perform_scan(self) -> List[WiFiMeasurement]:
        """Perform a single WiFi scan."""
        measurements = []
        
        try:
            # Try different scanning methods based on OS
            import platform
            
            if platform.system() == "Linux":
                measurements = self._scan_linux()
            elif platform.system() == "Darwin":  # macOS
                measurements = self._scan_macos()
            elif platform.system() == "Windows":
                measurements = self._scan_windows()
            else:
                logger.warning(f"Unsupported OS: {platform.system()}")
                
        except Exception as e:
            logger.error(f"Scan failed: {e}")
        
        return measurements
    
    def _scan_linux(self) -> List[WiFiMeasurement]:
        """Scan WiFi networks on Linux using iwlist or nmcli."""
        measurements = []
        current_time = time.time()
        
        try:
            # Try nmcli first (more reliable)
            result = subprocess.run(
                ["nmcli", "dev", "wifi", "list", "--rescan", "yes"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                measurements = self._parse_nmcli_output(result.stdout, current_time)
            else:
                # Fallback to iwlist
                measurements = self._scan_linux_iwlist(current_time)
                
        except subprocess.TimeoutExpired:
            logger.warning("WiFi scan timeout")
        except FileNotFoundError:
            # nmcli not available, try iwlist
            measurements = self._scan_linux_iwlist(current_time)
        
        return measurements
    
    def _scan_linux_iwlist(self, timestamp: float) -> List[WiFiMeasurement]:
        """Scan using iwlist on Linux."""
        measurements = []
        
        try:
            result = subprocess.run(
                ["sudo", "iwlist", self.interface, "scan"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                measurements = self._parse_iwlist_output(result.stdout, timestamp)
                
        except Exception as e:
            logger.error(f"iwlist scan failed: {e}")
        
        return measurements
    
    def _scan_macos(self) -> List[WiFiMeasurement]:
        """Scan WiFi networks on macOS."""
        measurements = []
        current_time = time.time()
        
        try:
            # First try airport if available
            airport_paths = [
                "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport",
                "/usr/local/bin/airport"
            ]
            
            airport_result = None
            for airport_path in airport_paths:
                if os.path.exists(airport_path):
                    try:
                        airport_result = subprocess.run(
                            [airport_path, "-s"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if airport_result.returncode == 0:
                            measurements = self._parse_airport_output(airport_result.stdout, current_time)
                            if measurements:
                                return measurements
                    except Exception as e:
                        logger.debug(f"Airport scan failed with {airport_path}: {e}")
                        continue
            
            # Fallback to networksetup for macOS
            if not measurements:
                try:
                    # Get WiFi interface name
                    hw_result = subprocess.run(
                        ["networksetup", "-listallhardwareports"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    wifi_interface = None
                    if hw_result.returncode == 0:
                        lines = hw_result.stdout.split('\n')
                        for i, line in enumerate(lines):
                            if 'Wi-Fi' in line and i + 1 < len(lines):
                                device_line = lines[i + 1]
                                if 'Device:' in device_line:
                                    wifi_interface = device_line.split(':')[1].strip()
                                    break
                    
                    # Use detected interface or fallback to en0
                    if not wifi_interface:
                        wifi_interface = "en0"
                    
                    # Try to scan with system profiler for basic info
                    system_result = subprocess.run(
                        ["system_profiler", "SPAirPortDataType"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if system_result.returncode == 0:
                        measurements = self._parse_system_profiler_output(system_result.stdout, current_time)
                    
                except Exception as e:
                    logger.debug(f"NetworkSetup scan failed: {e}")
                    
                    # Final fallback - create synthetic measurements from interface statistics
                    try:
                        # Get current network info
                        wifi_info = subprocess.run(
                            ["networksetup", "-getairportnetwork", wifi_interface or "en0"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        
                        if wifi_info.returncode == 0 and "You are not associated with an AirPort network" not in wifi_info.stdout:
                            # Extract current network name
                            current_network = wifi_info.stdout.strip().replace("Current Wi-Fi Network: ", "")
                            
                            # Create a synthetic measurement for current network
                            measurement = WiFiMeasurement(
                                timestamp=current_time,
                                ssid=current_network,
                                bssid="unknown",
                                signal_strength=-50.0,  # Synthetic value
                                frequency=2400.0,       # Synthetic 2.4GHz
                                channel=6,              # Synthetic channel
                                interface=self.interface
                            )
                            measurements.append(measurement)
                            logger.info(f"Created synthetic measurement for current network: {current_network}")
                            
                    except Exception as e:
                        logger.debug(f"Fallback network info failed: {e}")
                
        except Exception as e:
            logger.error(f"macOS WiFi scan failed: {e}")
        
        return measurements
    
    def _scan_windows(self) -> List[WiFiMeasurement]:
        """Scan WiFi networks on Windows using TP-Link and other WiFi dongles."""
        measurements = []
        current_time = time.time()
        
        try:
            # Use the proper netsh command to scan for networks with signal strength
            result = subprocess.run(
                ["netsh", "wlan", "show", "network", "mode=bssid"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                measurements = self._parse_netsh_output(result.stdout, current_time)
                logger.debug(f"Windows WiFi scan completed: {len(measurements)} networks found")
            else:
                logger.warning(f"netsh command failed with return code: {result.returncode}")
                
        except Exception as e:
            logger.error(f"Windows WiFi scan failed: {e}")
        
        return measurements
    
    def _parse_nmcli_output(self, output: str, timestamp: float) -> List[WiFiMeasurement]:
        """Parse nmcli scan output."""
        measurements = []
        lines = output.strip().split('\n')[1:]  # Skip header
        
        for line in lines:
            try:
                # nmcli output format varies, but generally:
                # SSID MODE CHAN RATE SIGNAL BARS SECURITY
                parts = line.split()
                if len(parts) >= 6:
                    ssid = parts[0] if parts[0] != '--' else "Unknown"
                    signal_str = parts[4]
                    
                    # Extract signal strength
                    signal_match = re.search(r'(-?\d+)', signal_str)
                    if signal_match:
                        signal_strength = float(signal_match.group(1))
                        
                        measurement = WiFiMeasurement(
                            timestamp=timestamp,
                            ssid=ssid,
                            bssid="unknown",  # nmcli doesn't always show BSSID
                            signal_strength=signal_strength,
                            frequency=0.0,  # Not available in basic nmcli output
                            channel=0,
                            interface=self.interface
                        )
                        measurements.append(measurement)
                        
            except Exception as e:
                logger.debug(f"Failed to parse line: {line}, error: {e}")
        
        return measurements
    
    def _parse_iwlist_output(self, output: str, timestamp: float) -> List[WiFiMeasurement]:
        """Parse iwlist scan output."""
        measurements = []
        current_cell = {}
        
        for line in output.split('\n'):
            line = line.strip()
            
            if "Cell" in line and "Address:" in line:
                # Start of new cell, save previous if complete
                if current_cell and 'ssid' in current_cell and 'signal' in current_cell:
                    measurements.append(self._create_measurement_from_cell(current_cell, timestamp))
                
                # Extract BSSID
                bssid_match = re.search(r'Address: ([a-fA-F0-9:]{17})', line)
                current_cell = {'bssid': bssid_match.group(1) if bssid_match else 'unknown'}
            
            elif "ESSID:" in line:
                ssid_match = re.search(r'ESSID:"([^"]*)"', line)
                current_cell['ssid'] = ssid_match.group(1) if ssid_match else 'unknown'
            
            elif "Signal level=" in line:
                signal_match = re.search(r'Signal level=(-?\d+)', line)
                if signal_match:
                    current_cell['signal'] = float(signal_match.group(1))
            
            elif "Frequency:" in line:
                freq_match = re.search(r'Frequency:(\d+\.?\d*)', line)
                if freq_match:
                    current_cell['frequency'] = float(freq_match.group(1)) * 1000  # Convert to MHz
        
        # Add last cell
        if current_cell and 'ssid' in current_cell and 'signal' in current_cell:
            measurements.append(self._create_measurement_from_cell(current_cell, timestamp))
        
        return measurements
    
    def _create_measurement_from_cell(self, cell: Dict, timestamp: float) -> WiFiMeasurement:
        """Create WiFiMeasurement from parsed cell data."""
        return WiFiMeasurement(
            timestamp=timestamp,
            ssid=cell.get('ssid', 'unknown'),
            bssid=cell.get('bssid', 'unknown'),
            signal_strength=cell.get('signal', 0.0),
            frequency=cell.get('frequency', 0.0),
            channel=0,  # Could calculate from frequency
            interface=self.interface
        )
    
    def _parse_airport_output(self, output: str, timestamp: float) -> List[WiFiMeasurement]:
        """Parse macOS airport scan output."""
        measurements = []
        lines = output.strip().split('\n')
        
        for line in lines:
            try:
                # Airport output format (varies by version)
                parts = line.split()
                if len(parts) >= 6:
                    ssid = parts[0]
                    bssid = parts[1]
                    signal_strength = float(parts[2])
                    
                    measurement = WiFiMeasurement(
                        timestamp=timestamp,
                        ssid=ssid,
                        bssid=bssid,
                        signal_strength=signal_strength,
                        frequency=0.0,
                        channel=0,
                        interface=self.interface
                    )
                    measurements.append(measurement)
                    
            except Exception as e:
                logger.debug(f"Failed to parse airport line: {line}, error: {e}")
        
        return measurements
    
    def _parse_system_profiler_output(self, output: str, timestamp: float) -> List[WiFiMeasurement]:
        """Parse macOS system_profiler SPAirPortDataType output."""
        measurements = []
        
        try:
            # Look for the current network in system profiler output
            lines = output.split('\n')
            current_network = None
            current_bssid = None
            signal_noise_ratio = None
            
            for line in lines:
                line = line.strip()
                
                # Look for current network
                if 'Current Network Information:' in line or 'Connected to:' in line:
                    # Next few lines contain network info
                    continue
                    
                # Extract network name
                if line.startswith('PHY Mode:') or line.startswith('BSSID:'):
                    # Previous pattern may vary, look for connected network differently
                    continue
                    
                # Try to find active network name
                if ': On' in line and not current_network:
                    # Extract network name before ': On'
                    network_name = line.split(': On')[0].strip()
                    if network_name and not network_name.startswith('AirPort'):
                        current_network = network_name
                        
                # Extract BSSID
                if 'BSSID:' in line:
                    bssid_match = re.search(r'BSSID:\s*([a-fA-F0-9:]{17})', line)
                    if bssid_match:
                        current_bssid = bssid_match.group(1)
                        
                # Extract signal information
                if 'Signal / Noise:' in line:
                    signal_match = re.search(r'Signal / Noise:\s*(-?\d+)', line)
                    if signal_match:
                        signal_noise_ratio = float(signal_match.group(1))
            
            # Create measurement if we found network info
            if current_network:
                measurement = WiFiMeasurement(
                    timestamp=timestamp,
                    ssid=current_network,
                    bssid=current_bssid or "unknown",
                    signal_strength=signal_noise_ratio or -50.0,  # Default if not found
                    frequency=2400.0,  # Default to 2.4GHz
                    channel=6,         # Default channel
                    interface=self.interface
                )
                measurements.append(measurement)
                logger.debug(f"System profiler found network: {current_network}")
                
        except Exception as e:
            logger.debug(f"Failed to parse system profiler output: {e}")
            
        return measurements
    
    def _parse_netsh_output(self, output: str, timestamp: float) -> List[WiFiMeasurement]:
        """Parse Windows netsh output for TP-Link and other WiFi dongles."""
        measurements = []
        
        try:
            lines = output.strip().split('\n')
            current_ssid = None
            current_bssid = None
            
            for line in lines:
                line = line.strip()
                
                # Parse SSID
                if line.startswith('SSID') and ':' in line:
                    current_ssid = line.split(':', 1)[1].strip()
                    if current_ssid and current_ssid != "<None>":
                        continue
                
                # Parse BSSID
                elif line.startswith('BSSID') and ':' in line and current_ssid:
                    current_bssid = line.split(':', 1)[1].strip()
                    
                # Parse Signal strength
                elif line.startswith('Signal') and ':' in line and current_ssid and current_bssid:
                    signal_str = line.split(':', 1)[1].strip().replace('%', '')
                    try:
                        signal_percent = float(signal_str)
                        # Convert percentage to approximate dBm (rough conversion)
                        signal_dbm = -100 + (signal_percent * 0.7)  # Rough approximation
                        
                        measurement = WiFiMeasurement(
                            timestamp=timestamp,
                            ssid=current_ssid,
                            bssid=current_bssid,
                            signal_strength=signal_dbm,
                            frequency=2400,  # Default to 2.4GHz
                            channel=1,  # Will be parsed separately if needed
                            interface="wlan0"  # Default interface name
                        )
                        measurements.append(measurement)
                        logger.debug(f"WiFi measurement: {current_ssid} ({current_bssid}) = {signal_dbm:.1f} dBm")
                        
                    except ValueError:
                        pass
                        
                    # Reset for next network
                    current_ssid = None
                    current_bssid = None
            
            if measurements:
                logger.info(f"Successfully parsed {len(measurements)} WiFi networks from TP-Link dongle")
            else:
                logger.warning("No valid WiFi measurements found in netsh output")
                
        except Exception as e:
            logger.error(f"Error parsing Windows netsh output: {e}")
            
        return measurements
    
    def get_latest_measurements(self, max_count: int = 100) -> List[WiFiMeasurement]:
        """Get latest measurements from queue."""
        measurements = []
        
        try:
            while len(measurements) < max_count:
                measurement = self.measurement_queue.get_nowait()
                measurements.append(measurement)
        except queue.Empty:
            pass
        
        return measurements
    
    def get_measurement_history(self, ssid_bssid: str = None) -> List[WiFiMeasurement]:
        """Get measurement history for analysis."""
        if ssid_bssid:
            return list(self.measurement_history.get(ssid_bssid, []))
        else:
            # Return all measurements
            all_measurements = []
            for measurements in self.measurement_history.values():
                all_measurements.extend(measurements)
            return sorted(all_measurements, key=lambda x: x.timestamp)


class WiFiFeatureExtractor:
    """Extract features from WiFi measurements for ML."""
    
    def __init__(self, window_size: float = 5.0, overlap: float = 0.5):
        """
        Initialize feature extractor.
        
        Args:
            window_size: Time window size in seconds
            overlap: Overlap ratio between windows (0-1)
        """
        self.window_size = window_size
        self.overlap = overlap
        self.step_size = window_size * (1 - overlap)
    
    def extract_features(self, measurements: List[WiFiMeasurement]) -> pd.DataFrame:
        """
        Extract features from WiFi measurements.
        
        Args:
            measurements: List of WiFi measurements
            
        Returns:
            DataFrame with extracted features
        """
        if not measurements:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame([asdict(m) for m in measurements])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.sort_values('timestamp')
        
        # Extract features for each SSID-BSSID pair
        features_list = []
        
        for (ssid, bssid), group in df.groupby(['ssid', 'bssid']):
            ssid_features = self._extract_ssid_features(group, ssid, bssid)
            features_list.extend(ssid_features)
        
        if features_list:
            return pd.DataFrame(features_list)
        else:
            return pd.DataFrame()
    
    def _extract_ssid_features(self, df: pd.DataFrame, ssid: str, bssid: str) -> List[Dict]:
        """Extract features for a specific SSID-BSSID pair."""
        features_list = []
        
        # Create time windows
        start_time = df['timestamp'].min()
        end_time = df['timestamp'].max()
        
        current_time = start_time
        window_id = 0
        
        while current_time + pd.Timedelta(seconds=self.window_size) <= end_time:
            window_end = current_time + pd.Timedelta(seconds=self.window_size)
            
            # Get data in current window
            window_data = df[
                (df['timestamp'] >= current_time) & 
                (df['timestamp'] < window_end)
            ]
            
            if len(window_data) > 0:
                features = self._compute_window_features(window_data, ssid, bssid, window_id)
                features_list.append(features)
            
            current_time += pd.Timedelta(seconds=self.step_size)
            window_id += 1
        
        return features_list
    
    def _compute_window_features(self, window_data: pd.DataFrame, ssid: str, 
                                bssid: str, window_id: int) -> Dict:
        """Compute features for a single time window."""
        signal_values = window_data['signal_strength'].values
        
        features = {
            'window_id': window_id,
            'ssid': ssid,
            'bssid': bssid,
            'timestamp': window_data['timestamp'].mean().timestamp(),
            'measurement_count': len(signal_values),
            
            # Basic statistical features
            'rssi_mean': np.mean(signal_values),
            'rssi_std': np.std(signal_values),
            'rssi_var': np.var(signal_values),
            'rssi_min': np.min(signal_values),
            'rssi_max': np.max(signal_values),
            'rssi_range': np.max(signal_values) - np.min(signal_values),
            'rssi_median': np.median(signal_values),
            
            # Higher order statistics
            'rssi_skewness': self._safe_skewness(signal_values),
            'rssi_kurtosis': self._safe_kurtosis(signal_values),
            
            # Temporal features
            'rssi_slope': self._compute_slope(signal_values),
            'rssi_volatility': self._compute_volatility(signal_values),
            
            # Frequency domain features (if enough samples)
            'rssi_dominant_freq': self._compute_dominant_frequency(signal_values),
            'rssi_spectral_centroid': self._compute_spectral_centroid(signal_values)
        }
        
        return features
    
    def _safe_skewness(self, values: np.ndarray) -> float:
        """Compute skewness safely."""
        try:
            from scipy.stats import skew
            return float(skew(values))
        except:
            return 0.0
    
    def _safe_kurtosis(self, values: np.ndarray) -> float:
        """Compute kurtosis safely."""
        try:
            from scipy.stats import kurtosis
            return float(kurtosis(values))
        except:
            return 0.0
    
    def _compute_slope(self, values: np.ndarray) -> float:
        """Compute slope of signal strength over time."""
        if len(values) < 2:
            return 0.0
        
        x = np.arange(len(values))
        try:
            slope = np.polyfit(x, values, 1)[0]
            return float(slope)
        except:
            return 0.0
    
    def _compute_volatility(self, values: np.ndarray) -> float:
        """Compute signal volatility (rate of change)."""
        if len(values) < 2:
            return 0.0
        
        diff = np.diff(values)
        return float(np.std(diff))
    
    def _compute_dominant_frequency(self, values: np.ndarray) -> float:
        """Compute dominant frequency using FFT."""
        if len(values) < 4:
            return 0.0
        
        try:
            fft = np.fft.fft(values - np.mean(values))
            freqs = np.fft.fftfreq(len(values))
            
            # Find peak frequency
            magnitudes = np.abs(fft)
            peak_idx = np.argmax(magnitudes[1:len(magnitudes)//2]) + 1
            
            return float(freqs[peak_idx])
        except:
            return 0.0
    
    def _compute_spectral_centroid(self, values: np.ndarray) -> float:
        """Compute spectral centroid."""
        if len(values) < 4:
            return 0.0
        
        try:
            fft = np.fft.fft(values - np.mean(values))
            freqs = np.fft.fftfreq(len(values))
            magnitudes = np.abs(fft)
            
            # Compute centroid
            centroid = np.sum(freqs * magnitudes) / np.sum(magnitudes)
            return float(centroid)
        except:
            return 0.0


class WiFiModule:
    """Main WiFi sensing module."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize WiFi module."""
        self.config = config
        
        # Initialize scanner
        self.scanner = WiFiScanner(config.get('rssi', {}))
        
        # Initialize feature extractor
        ml_config = config.get('ml', {})
        features_config = ml_config.get('features', {})
        
        self.feature_extractor = WiFiFeatureExtractor(
            window_size=features_config.get('window_size', 5.0),
            overlap=features_config.get('overlap', 0.5)
        )
        
        self.is_running = False
        logger.info("WiFi module initialized")
    
    def start(self) -> bool:
        """Start WiFi sensing."""
        success = self.scanner.start_scanning()
        if success:
            self.is_running = True
            logger.info("WiFi module started")
        return success
    
    def stop(self):
        """Stop WiFi sensing."""
        self.scanner.stop_scanning()
        self.is_running = False
        logger.info("WiFi module stopped")
    
    def get_current_measurements(self) -> List[WiFiMeasurement]:
        """Get current WiFi measurements."""
        return self.scanner.get_latest_measurements()
    
    def extract_recent_features(self, time_window: float = 30.0) -> pd.DataFrame:
        """Extract features from recent measurements."""
        # Get recent measurements
        all_measurements = self.scanner.get_measurement_history()
        
        # Filter to recent time window
        current_time = time.time()
        recent_measurements = [
            m for m in all_measurements 
            if (current_time - m.timestamp) <= time_window
        ]
        
        # Extract features
        return self.feature_extractor.extract_features(recent_measurements)
    
    def get_status(self) -> Dict[str, Any]:
        """Get WiFi module status."""
        measurements = self.scanner.get_latest_measurements(10)
        
        return {
            "is_running": self.is_running,
            "interface": self.scanner.interface,
            "recent_measurement_count": len(measurements),
            "unique_aps_detected": len(set(f"{m.ssid}_{m.bssid}" for m in measurements)),
            "average_signal_strength": np.mean([m.signal_strength for m in measurements]) if measurements else 0,
            "last_measurement_time": measurements[-1].timestamp if measurements else 0
        }


def main():
    """Test the WiFi module."""
    config = {
        'rssi': {
            'interface': 'wlan0',
            'scan_interval': 2.0,
            'target_ssids': []
        },
        'ml': {
            'features': {
                'window_size': 5.0,
                'overlap': 0.5
            }
        }
    }
    
    wifi_module = WiFiModule(config)
    
    if wifi_module.start():
        print("WiFi module started. Collecting data...")
        
        try:
            start_time = time.time()
            while time.time() - start_time < 60:  # Run for 1 minute
                measurements = wifi_module.get_current_measurements()
                
                if measurements:
                    print(f"\nDetected {len(measurements)} access points:")
                    for m in measurements[-5:]:  # Show last 5
                        print(f"  {m.ssid}: {m.signal_strength} dBm")
                
                # Extract features every 10 seconds
                if int(time.time() - start_time) % 10 == 0:
                    features = wifi_module.extract_recent_features(20.0)
                    if not features.empty:
                        print(f"\nExtracted features for {len(features)} windows")
                        print(features[['ssid', 'rssi_mean', 'rssi_std', 'rssi_volatility']].head())
                
                time.sleep(5)
                
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            wifi_module.stop()
    else:
        print("Failed to start WiFi module")


if __name__ == "__main__":
    main()