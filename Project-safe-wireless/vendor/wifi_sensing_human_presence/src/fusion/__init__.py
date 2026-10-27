"""
Data fusion and decision module for WiFi sensing human presence system.

This module combines camera detection results with WiFi sensing data to make
intelligent decisions about human presence, especially when the person is
not visible to the camera.
"""

import time
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import threading
import queue
from loguru import logger
import joblib
from pathlib import Path


class PresenceState(Enum):
    """Enumeration for possible presence states."""
    VISIBLE_CAMERA = "visible_camera"        # Person visible to camera
    BEHIND_WALL = "behind_wall"             # Person behind wall/door but still in area
    IN_ROOM_HIDDEN = "in_room_hidden"       # Person in room but not visible to camera
    LEFT_AREA = "left_area"                 # Person left the monitored area
    UNKNOWN = "unknown"                     # Cannot determine state


@dataclass
class FusionResult:
    """Result of data fusion and decision making."""
    timestamp: float
    presence_state: PresenceState
    confidence: float
    camera_person_visible: bool
    wifi_features_available: bool
    decision_source: str  # "camera", "wifi", or "fusion"
    additional_info: Dict[str, Any]


@dataclass
class SensorData:
    """Combined sensor data for decision making."""
    timestamp: float
    camera_detection: Optional[Dict[str, Any]]
    wifi_features: Optional[pd.DataFrame]
    wifi_measurements: Optional[List[Any]]


class RuleBasedDecision:
    """Rule-based decision making for presence detection."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize rule-based decision maker."""
        self.config = config
        
        # Thresholds
        self.camera_timeout = config.get("camera_timeout", 5.0)  # seconds
        self.wifi_change_threshold = config.get("wifi_change_threshold", 2.0)  # dB
        self.min_wifi_samples = config.get("min_wifi_samples", 5)
        
        # History for trend analysis
        self.wifi_history = []
        self.max_history_size = 20
        
        logger.info("Rule-based decision module initialized")
    
    def decide(self, sensor_data: SensorData) -> FusionResult:
        """
        Make presence decision using rules.
        
        Args:
            sensor_data: Combined sensor data
            
        Returns:
            FusionResult with decision
        """
        camera_detection = sensor_data.camera_detection
        wifi_features = sensor_data.wifi_features
        
        # Check camera first (highest priority when available)
        if camera_detection and camera_detection.get("person_visible", False):
            return FusionResult(
                timestamp=sensor_data.timestamp,
                presence_state=PresenceState.VISIBLE_CAMERA,
                confidence=0.95,
                camera_person_visible=True,
                wifi_features_available=wifi_features is not None,
                decision_source="camera",
                additional_info={"camera_detections": len(camera_detection.get("detections", []))}
            )
        
        # Camera doesn't see person - check if recently seen
        time_since_last_seen = float('inf')
        if camera_detection:
            time_since_last_seen = camera_detection.get("time_since_last_person", float('inf'))
        
        # If person was recently seen by camera, use WiFi to determine state
        if time_since_last_seen < self.camera_timeout:
            return self._decide_using_wifi(sensor_data, recently_seen=True)
        else:
            return self._decide_using_wifi(sensor_data, recently_seen=False)
    
    def _decide_using_wifi(self, sensor_data: SensorData, recently_seen: bool) -> FusionResult:
        """Make decision based on WiFi data."""
        wifi_features = sensor_data.wifi_features
        
        if wifi_features is None or wifi_features.empty:
            return FusionResult(
                timestamp=sensor_data.timestamp,
                presence_state=PresenceState.UNKNOWN,
                confidence=0.3,
                camera_person_visible=False,
                wifi_features_available=False,
                decision_source="wifi",
                additional_info={"reason": "no_wifi_data"}
            )
        
        # Analyze WiFi signal patterns
        wifi_analysis = self._analyze_wifi_patterns(wifi_features)
        
        # Update history
        self.wifi_history.append(wifi_analysis)
        if len(self.wifi_history) > self.max_history_size:
            self.wifi_history.pop(0)
        
        # Make decision based on WiFi patterns
        if wifi_analysis["strong_signal_change"]:
            if recently_seen:
                # Strong signal change + recently seen = likely behind wall
                state = PresenceState.BEHIND_WALL
                confidence = 0.8
            else:
                # Strong signal change + not recently seen = movement or entry
                state = PresenceState.IN_ROOM_HIDDEN
                confidence = 0.7
        
        elif wifi_analysis["moderate_signal_change"]:
            if recently_seen:
                # Moderate change + recently seen = possibly behind wall
                state = PresenceState.BEHIND_WALL
                confidence = 0.6
            else:
                # Moderate change = uncertain
                state = PresenceState.UNKNOWN
                confidence = 0.4
        
        else:
            # Minimal signal change
            if recently_seen:
                # Person might have left
                trend_analysis = self._analyze_trend()
                if trend_analysis["decreasing_activity"]:
                    state = PresenceState.LEFT_AREA
                    confidence = 0.7
                else:
                    state = PresenceState.BEHIND_WALL
                    confidence = 0.5
            else:
                # No recent sighting + no change = likely gone
                state = PresenceState.LEFT_AREA
                confidence = 0.8
        
        return FusionResult(
            timestamp=sensor_data.timestamp,
            presence_state=state,
            confidence=confidence,
            camera_person_visible=False,
            wifi_features_available=True,
            decision_source="wifi",
            additional_info={
                "wifi_analysis": wifi_analysis,
                "recently_seen": recently_seen
            }
        )
    
    def _analyze_wifi_patterns(self, wifi_features: pd.DataFrame) -> Dict[str, Any]:
        """Analyze WiFi signal patterns for presence indicators."""
        analysis = {
            "strong_signal_change": False,
            "moderate_signal_change": False,
            "high_volatility": False,
            "mean_signal_strength": 0.0,
            "max_volatility": 0.0,
            "ap_count": len(wifi_features)
        }
        
        if wifi_features.empty:
            return analysis
        
        # Analyze signal strength changes
        mean_rssi = wifi_features['rssi_mean'].mean()
        std_rssi = wifi_features['rssi_std'].mean()
        volatility = wifi_features['rssi_volatility'].mean()
        
        analysis["mean_signal_strength"] = mean_rssi
        analysis["max_volatility"] = volatility
        
        # Thresholds for signal changes (these would be tuned based on data)
        if volatility > 3.0:  # High volatility indicates movement
            analysis["strong_signal_change"] = True
            analysis["high_volatility"] = True
        elif volatility > 1.5:
            analysis["moderate_signal_change"] = True
        elif std_rssi > 2.0:  # High standard deviation
            analysis["moderate_signal_change"] = True
        
        return analysis
    
    def _analyze_trend(self) -> Dict[str, Any]:
        """Analyze trends in WiFi history."""
        trend_analysis = {
            "decreasing_activity": False,
            "increasing_activity": False,
            "stable_activity": True
        }
        
        if len(self.wifi_history) < 3:
            return trend_analysis
        
        # Analyze volatility trend
        recent_volatility = [h["max_volatility"] for h in self.wifi_history[-5:]]
        older_volatility = [h["max_volatility"] for h in self.wifi_history[-10:-5]] if len(self.wifi_history) >= 10 else []
        
        if older_volatility and recent_volatility:
            recent_avg = np.mean(recent_volatility)
            older_avg = np.mean(older_volatility)
            
            if recent_avg < 0.5 * older_avg:
                trend_analysis["decreasing_activity"] = True
                trend_analysis["stable_activity"] = False
            elif recent_avg > 2.0 * older_avg:
                trend_analysis["increasing_activity"] = True
                trend_analysis["stable_activity"] = False
        
        return trend_analysis


class MLBasedDecision:
    """Machine learning based decision making."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize ML-based decision maker."""
        self.config = config
        self.model = None
        self.model_path = config.get("model_path", "models/presence_classifier.joblib")
        self.feature_columns = None
        self.is_trained = False
        
        # Try to load existing model
        self._load_model()
        
        logger.info("ML-based decision module initialized")
    
    def _load_model(self) -> bool:
        """Load trained model if available."""
        try:
            model_path = Path(self.model_path)
            if model_path.exists():
                model_data = joblib.load(model_path)
                self.model = model_data['model']
                self.feature_columns = model_data.get('feature_columns', None)
                self.is_trained = True
                logger.info(f"Loaded trained model from {model_path}")
                return True
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
        
        return False
    
    def decide(self, sensor_data: SensorData) -> FusionResult:
        """
        Make presence decision using ML model.
        
        Args:
            sensor_data: Combined sensor data
            
        Returns:
            FusionResult with decision
        """
        if not self.is_trained or self.model is None:
            return FusionResult(
                timestamp=sensor_data.timestamp,
                presence_state=PresenceState.UNKNOWN,
                confidence=0.0,
                camera_person_visible=False,
                wifi_features_available=False,
                decision_source="ml",
                additional_info={"reason": "model_not_trained"}
            )
        
        # Check camera first
        camera_detection = sensor_data.camera_detection
        if camera_detection and camera_detection.get("person_visible", False):
            return FusionResult(
                timestamp=sensor_data.timestamp,
                presence_state=PresenceState.VISIBLE_CAMERA,
                confidence=0.95,
                camera_person_visible=True,
                wifi_features_available=sensor_data.wifi_features is not None,
                decision_source="camera",
                additional_info={}
            )
        
        # Use ML model for WiFi-based decision
        wifi_features = sensor_data.wifi_features
        if wifi_features is None or wifi_features.empty:
            return FusionResult(
                timestamp=sensor_data.timestamp,
                presence_state=PresenceState.UNKNOWN,
                confidence=0.2,
                camera_person_visible=False,
                wifi_features_available=False,
                decision_source="ml",
                additional_info={"reason": "no_wifi_features"}
            )
        
        # Prepare features for model
        try:
            features_for_model = self._prepare_features(wifi_features, camera_detection)
            
            # Make prediction
            prediction_proba = self.model.predict_proba(features_for_model)
            predicted_class = self.model.predict(features_for_model)[0]
            confidence = np.max(prediction_proba[0])
            
            # Map class to PresenceState
            state_mapping = {
                0: PresenceState.LEFT_AREA,
                1: PresenceState.BEHIND_WALL,
                2: PresenceState.IN_ROOM_HIDDEN
            }
            
            predicted_state = state_mapping.get(predicted_class, PresenceState.UNKNOWN)
            
            return FusionResult(
                timestamp=sensor_data.timestamp,
                presence_state=predicted_state,
                confidence=confidence,
                camera_person_visible=False,
                wifi_features_available=True,
                decision_source="ml",
                additional_info={
                    "prediction_proba": prediction_proba[0].tolist(),
                    "predicted_class": int(predicted_class)
                }
            )
            
        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            return FusionResult(
                timestamp=sensor_data.timestamp,
                presence_state=PresenceState.UNKNOWN,
                confidence=0.0,
                camera_person_visible=False,
                wifi_features_available=True,
                decision_source="ml",
                additional_info={"reason": "prediction_error", "error": str(e)}
            )
    
    def _prepare_features(self, wifi_features: pd.DataFrame, 
                         camera_detection: Optional[Dict[str, Any]]) -> np.ndarray:
        """Prepare features for ML model."""
        # Aggregate WiFi features
        agg_features = {}
        
        if not wifi_features.empty:
            # Aggregate across all APs
            numeric_columns = wifi_features.select_dtypes(include=[np.number]).columns
            for col in numeric_columns:
                if col not in ['window_id', 'timestamp']:
                    agg_features[f"{col}_mean"] = wifi_features[col].mean()
                    agg_features[f"{col}_std"] = wifi_features[col].std()
                    agg_features[f"{col}_max"] = wifi_features[col].max()
                    agg_features[f"{col}_min"] = wifi_features[col].min()
        
        # Add camera-related features
        if camera_detection:
            agg_features["time_since_last_person"] = camera_detection.get("time_since_last_person", 0)
            agg_features["was_recently_visible"] = 1 if camera_detection.get("time_since_last_person", float('inf')) < 10 else 0
        else:
            agg_features["time_since_last_person"] = float('inf')
            agg_features["was_recently_visible"] = 0
        
        # Convert to DataFrame and align with training features
        feature_df = pd.DataFrame([agg_features])
        
        if self.feature_columns is not None:
            # Ensure all training features are present
            for col in self.feature_columns:
                if col not in feature_df.columns:
                    feature_df[col] = 0.0
            
            # Select only training features in the same order
            feature_df = feature_df[self.feature_columns]
        
        return feature_df.values


class DataFusionModule:
    """Main data fusion module that combines camera and WiFi data."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize data fusion module."""
        self.config = config
        
        # Decision strategy
        strategy = config.get("strategy", "rule_based")  # "rule_based" or "ml"
        
        if strategy == "ml":
            self.decision_maker = MLBasedDecision(config.get("ml", {}))
        else:
            self.decision_maker = RuleBasedDecision(config.get("rules", {}))
        
        # Data buffers
        self.camera_data_queue = queue.Queue(maxsize=100)
        self.wifi_data_queue = queue.Queue(maxsize=100)
        self.fusion_results_queue = queue.Queue(maxsize=100)
        
        # Processing thread
        self.is_running = False
        self.fusion_thread = None
        
        # State tracking
        self.last_fusion_result = None
        self.fusion_count = 0
        
        logger.info(f"Data fusion module initialized with strategy: {strategy}")
    
    def start(self) -> bool:
        """Start data fusion processing."""
        try:
            self.is_running = True
            self.fusion_thread = threading.Thread(target=self._fusion_loop)
            self.fusion_thread.daemon = True
            self.fusion_thread.start()
            
            logger.info("Data fusion module started")
            return True
        except Exception as e:
            logger.error(f"Failed to start data fusion: {e}")
            return False
    
    def stop(self):
        """Stop data fusion processing."""
        self.is_running = False
        if self.fusion_thread and self.fusion_thread.is_alive():
            self.fusion_thread.join(timeout=2)
        logger.info("Data fusion module stopped")
    
    def add_camera_data(self, camera_data: Dict[str, Any]):
        """Add camera detection data."""
        if not self.camera_data_queue.full():
            self.camera_data_queue.put(camera_data)
    
    def add_wifi_data(self, wifi_features: pd.DataFrame, wifi_measurements: List[Any]):
        """Add WiFi sensing data."""
        wifi_data = {
            "timestamp": time.time(),
            "features": wifi_features,
            "measurements": wifi_measurements
        }
        
        if not self.wifi_data_queue.full():
            self.wifi_data_queue.put(wifi_data)
    
    def _fusion_loop(self):
        """Main fusion processing loop."""
        while self.is_running:
            try:
                # Get latest data from both sources
                camera_data = self._get_latest_data(self.camera_data_queue, timeout=1.0)
                wifi_data = self._get_latest_data(self.wifi_data_queue, timeout=0.1)
                
                # Create sensor data object
                sensor_data = SensorData(
                    timestamp=time.time(),
                    camera_detection=camera_data,
                    wifi_features=wifi_data.get("features") if wifi_data else None,
                    wifi_measurements=wifi_data.get("measurements") if wifi_data else None
                )
                
                # Make fusion decision
                fusion_result = self.decision_maker.decide(sensor_data)
                self.last_fusion_result = fusion_result
                self.fusion_count += 1
                
                # Store result
                if not self.fusion_results_queue.full():
                    self.fusion_results_queue.put(fusion_result)
                
                # Log significant state changes
                if self._is_significant_change(fusion_result):
                    logger.info(f"Presence state: {fusion_result.presence_state.value} "
                              f"(confidence: {fusion_result.confidence:.2f}, "
                              f"source: {fusion_result.decision_source})")
                
                time.sleep(0.5)  # Process every 0.5 seconds
                
            except Exception as e:
                logger.error(f"Error in fusion loop: {e}")
                time.sleep(1)
    
    def _get_latest_data(self, data_queue: queue.Queue, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Get the latest data from queue, discarding older data."""
        latest_data = None
        
        try:
            # Get all available data, keeping only the latest
            while True:
                data = data_queue.get(timeout=timeout)
                latest_data = data
        except queue.Empty:
            pass
        
        return latest_data
    
    def _is_significant_change(self, fusion_result: FusionResult) -> bool:
        """Check if this represents a significant state change."""
        if self.last_fusion_result is None:
            return True
        
        # Check for state change
        if fusion_result.presence_state != self.last_fusion_result.presence_state:
            return True
        
        # Check for confidence change
        confidence_change = abs(fusion_result.confidence - self.last_fusion_result.confidence)
        if confidence_change > 0.3:
            return True
        
        return False
    
    def get_latest_result(self) -> Optional[FusionResult]:
        """Get the latest fusion result."""
        return self.last_fusion_result
    
    def get_all_recent_results(self, max_count: int = 10) -> List[FusionResult]:
        """Get recent fusion results."""
        results = []
        
        try:
            while len(results) < max_count:
                result = self.fusion_results_queue.get_nowait()
                results.append(result)
        except queue.Empty:
            pass
        
        return results[::-1]  # Return in chronological order
    
    def get_status(self) -> Dict[str, Any]:
        """Get fusion module status."""
        return {
            "is_running": self.is_running,
            "fusion_count": self.fusion_count,
            "last_result": {
                "state": self.last_fusion_result.presence_state.value if self.last_fusion_result else None,
                "confidence": self.last_fusion_result.confidence if self.last_fusion_result else 0,
                "timestamp": self.last_fusion_result.timestamp if self.last_fusion_result else 0
            },
            "camera_queue_size": self.camera_data_queue.qsize(),
            "wifi_queue_size": self.wifi_data_queue.qsize(),
            "results_queue_size": self.fusion_results_queue.qsize()
        }


def main():
    """Test the data fusion module."""
    config = {
        "strategy": "rule_based",
        "rules": {
            "camera_timeout": 5.0,
            "wifi_change_threshold": 2.0,
            "min_wifi_samples": 5
        }
    }
    
    fusion_module = DataFusionModule(config)
    
    if fusion_module.start():
        print("Data fusion module started. Testing with simulated data...")
        
        try:
            # Simulate data for testing
            for i in range(20):
                # Simulate camera data
                camera_data = {
                    "person_visible": i < 5,  # Person visible for first 5 iterations
                    "time_since_last_person": max(0, i - 5),
                    "detections": [{"confidence": 0.8}] if i < 5 else []
                }
                
                # Simulate WiFi data
                wifi_features = pd.DataFrame({
                    "rssi_mean": [-60 + np.random.normal(0, 5, 1)[0]],
                    "rssi_std": [2 + np.random.normal(0, 1, 1)[0]],
                    "rssi_volatility": [1 + np.random.exponential(1, 1)[0]]
                })
                
                fusion_module.add_camera_data(camera_data)
                fusion_module.add_wifi_data(wifi_features, [])
                
                time.sleep(1)
                
                # Check result
                result = fusion_module.get_latest_result()
                if result:
                    print(f"Iteration {i}: {result.presence_state.value} "
                          f"(confidence: {result.confidence:.2f})")
            
            # Print final status
            status = fusion_module.get_status()
            print(f"\nFinal status: {status}")
            
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            fusion_module.stop()
    else:
        print("Failed to start data fusion module")


if __name__ == "__main__":
    main()