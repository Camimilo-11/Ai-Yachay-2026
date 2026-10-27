"""
Configuration loader and utilities for WiFi sensing system.
"""

import yaml
import json
from typing import Dict, Any, Optional
from pathlib import Path
from loguru import logger


class ConfigLoader:
    """Configuration loader with validation and defaults."""
    
    def __init__(self):
        """Initialize config loader."""
        self.default_config = self._get_default_config()
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from file with fallback to defaults.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            logger.warning(f"Config file {config_path} not found, using defaults")
            return self.default_config.copy()
        
        try:
            with open(config_file, 'r') as f:
                if config_file.suffix.lower() == '.yaml' or config_file.suffix.lower() == '.yml':
                    loaded_config = yaml.safe_load(f)
                elif config_file.suffix.lower() == '.json':
                    loaded_config = json.load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {config_file.suffix}")
            
            # Merge with defaults
            merged_config = self._merge_configs(self.default_config, loaded_config)
            
            # Validate configuration
            self._validate_config(merged_config)
            
            logger.info(f"Configuration loaded from {config_path}")
            return merged_config
            
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
            logger.info("Using default configuration")
            return self.default_config.copy()
    
    def save_config(self, config: Dict[str, Any], output_path: str):
        """Save configuration to file."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_file, 'w') as f:
                if output_file.suffix.lower() == '.yaml' or output_file.suffix.lower() == '.yml':
                    yaml.safe_dump(config, f, indent=2, default_flow_style=False)
                elif output_file.suffix.lower() == '.json':
                    json.dump(config, f, indent=2)
                else:
                    raise ValueError(f"Unsupported output format: {output_file.suffix}")
            
            logger.info(f"Configuration saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error saving config to {output_path}: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "camera": {
                "device_id": 0,
                "width": 640,
                "height": 480,
                "fps": 30,
                "person_detection": {
                    "confidence_threshold": 0.5,
                    "nms_threshold": 0.4
                }
            },
            "wifi": {
                "data_type": "rssi",
                "rssi": {
                    "interface": "wlan0",
                    "scan_interval": 1.0,
                    "target_ssids": []
                },
                "csi": {
                    "device_type": "intel5300",
                    "sampling_rate": 20,
                    "esp32": {
                        "serial_port": "/dev/ttyUSB0",
                        "baud_rate": 115200
                    }
                }
            },
            "ml": {
                "features": {
                    "window_size": 5.0,
                    "overlap": 0.5,
                    "rssi_features": [
                        "mean", "std", "variance", "range", "skewness", "kurtosis"
                    ]
                },
                "model": {
                    "type": "random_forest",
                    "random_forest": {
                        "n_estimators": 100,
                        "max_depth": 10,
                        "random_state": 42
                    }
                },
                "training": {
                    "test_size": 0.2,
                    "validation_size": 0.1,
                    "cross_validation_folds": 5
                }
            },
            "fusion": {
                "strategy": "rule_based",
                "rules": {
                    "camera_timeout": 5.0,
                    "wifi_change_threshold": 2.0,
                    "min_wifi_samples": 5
                }
            },
            "data_collection": {
                "session_duration": 300,
                "data_dir": "data/raw",
                "labels": [
                    "visible_camera",
                    "behind_wall", 
                    "in_room_hidden",
                    "left_area"
                ]
            },
            "system": {
                "log_level": "INFO",
                "log_file": "logs/wifi_sensing.log",
                "save_raw_data": True,
                "data_retention_days": 30
            },
            "privacy": {
                "consent_required": True,
                "anonymize_data": True,
                "max_recording_duration": 3600,
                "delete_video_after_processing": True
            }
        }
    
    def _merge_configs(self, default: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge loaded config with defaults."""
        merged = default.copy()
        
        for key, value in loaded.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_configs(merged[key], value)
            else:
                merged[key] = value
        
        return merged
    
    def _validate_config(self, config: Dict[str, Any]):
        """Validate configuration values."""
        # Camera validation
        camera_config = config.get("camera", {})
        if camera_config.get("width", 0) <= 0 or camera_config.get("height", 0) <= 0:
            raise ValueError("Camera width and height must be positive")
        
        if camera_config.get("fps", 0) <= 0:
            raise ValueError("Camera FPS must be positive")
        
        # ML validation
        ml_config = config.get("ml", {})
        features_config = ml_config.get("features", {})
        
        if features_config.get("window_size", 0) <= 0:
            raise ValueError("ML window_size must be positive")
        
        if not 0 <= features_config.get("overlap", 0.5) < 1:
            raise ValueError("ML overlap must be between 0 and 1")
        
        # Training validation
        training_config = ml_config.get("training", {})
        if not 0 < training_config.get("test_size", 0.2) < 1:
            raise ValueError("Training test_size must be between 0 and 1")
        
        logger.debug("Configuration validation passed")