"""Clases extraídas de IsukaW, revisión 91aee04, licencia MIT en vendor/.
Lógica de clases conservada; se omiten escáner y dependencias de hardware.
"""
from dataclasses import dataclass, asdict
from typing import Dict, List, Any
import numpy as np
import pandas as pd
import scipy.stats  # Requisito explícito para momentos estadísticos.

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

