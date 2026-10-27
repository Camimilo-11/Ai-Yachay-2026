#!/usr/bin/env python3
"""
Data collection script for WiFi sensing human presence detection.

This script orchestrates synchronized collection of camera detection data
and WiFi sensing measurements along with ground truth labels for training
machine learning models.
"""

import os
import sys
import time
import json
import csv
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import threading
import queue
import signal
from dataclasses import dataclass, asdict

# Add src directory to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from camera import CameraModule
from wifi import WiFiModule
from utils.config_loader import ConfigLoader
from loguru import logger
import pandas as pd
import numpy as np
import yaml


@dataclass
class CollectionSession:
    """Data collection session metadata."""
    session_id: str
    start_time: float
    end_time: Optional[float]
    participant_id: str
    scenario: str
    environment: str
    notes: str
    data_files: List[str]


@dataclass
class LabeledDataPoint:
    """Single labeled data point."""
    timestamp: float
    session_id: str
    label: str
    camera_data: Dict[str, Any]
    wifi_features: Dict[str, Any]
    wifi_measurements: List[Dict[str, Any]]
    manual_annotation: str


class DataCollector:
    """Main data collection coordinator."""
    
    def __init__(self, config: Dict[str, Any], output_dir: str = "data/raw"):
        """
        Initialize data collector.
        
        Args:
            config: System configuration
            output_dir: Directory to save collected data
        """
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize modules
        self.camera_module = CameraModule(config.get("camera", {}))
        self.wifi_module = WiFiModule(config.get("wifi", {}))
        
        # Collection state
        self.is_collecting = False
        self.current_session = None
        self.collection_thread = None
        
        # Data buffers
        self.data_points = []
        self.max_buffer_size = 1000
        
        # Current label (set by user during collection)
        self.current_label = "unknown"
        self.label_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            "total_samples": 0,
            "samples_per_label": {},
            "start_time": 0,
            "collection_duration": 0
        }
        
        logger.info(f"Data collector initialized. Output dir: {self.output_dir}")
    
    def start_collection(self, session_config: Dict[str, Any]) -> str:
        """
        Start data collection session.
        
        Args:
            session_config: Session configuration
            
        Returns:
            Session ID
        """
        # Generate session ID
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create session
        self.current_session = CollectionSession(
            session_id=session_id,
            start_time=time.time(),
            end_time=None,
            participant_id=session_config.get("participant_id", "unknown"),
            scenario=session_config.get("scenario", "general"),
            environment=session_config.get("environment", "unknown"),
            notes=session_config.get("notes", ""),
            data_files=[]
        )
        
        # Start modules
        camera_started = self.camera_module.start()
        wifi_started = self.wifi_module.start()
        
        if not (camera_started and wifi_started):
            logger.error("Failed to start one or more modules")
            return ""
        
        # Start collection thread
        self.is_collecting = True
        self.collection_thread = threading.Thread(target=self._collection_loop)
        self.collection_thread.daemon = True
        self.collection_thread.start()
        
        # Reset statistics
        self.stats = {
            "total_samples": 0,
            "samples_per_label": {},
            "start_time": time.time(),
            "collection_duration": 0
        }
        
        logger.info(f"Data collection started for session: {session_id}")
        return session_id
    
    def stop_collection(self) -> Optional[str]:
        """
        Stop data collection and save data.
        
        Returns:
            Path to saved data file
        """
        if not self.is_collecting:
            return None
        
        # Stop collection
        self.is_collecting = False
        
        if self.collection_thread and self.collection_thread.is_alive():
            self.collection_thread.join(timeout=5)
        
        # Stop modules
        self.camera_module.stop()
        self.wifi_module.stop()
        
        # Update session
        if self.current_session:
            self.current_session.end_time = time.time()
            self.stats["collection_duration"] = self.current_session.end_time - self.current_session.start_time
        
        # Save data
        data_file = self._save_collected_data()
        
        logger.info(f"Data collection stopped. Collected {self.stats['total_samples']} samples"
                   f" in {self.stats['collection_duration']:.1f}s")
        
        return data_file
    
    def set_current_label(self, label: str):
        """Set the current label for data collection."""
        with self.label_lock:
            self.current_label = label
        logger.info(f"Current label set to: {label}")
    
    def _collection_loop(self):
        """Main data collection loop."""
        while self.is_collecting:
            try:
                # Get current timestamp
                timestamp = time.time()
                
                # Get camera data
                camera_detection = self.camera_module.get_latest_detection()
                camera_status = self.camera_module.get_current_status()
                
                # Combine camera data
                camera_data = {
                    "status": camera_status,
                    "detection": camera_detection
                }
                
                # Get WiFi data
                wifi_measurements = self.wifi_module.get_current_measurements()
                wifi_features_df = self.wifi_module.extract_recent_features(10.0)
                
                # Convert WiFi features to dict
                wifi_features = {}
                if not wifi_features_df.empty:
                    # Aggregate features across all APs
                    numeric_cols = wifi_features_df.select_dtypes(include=[np.number]).columns
                    for col in numeric_cols:
                        if col not in ['window_id', 'timestamp']:
                            wifi_features[f"{col}_mean"] = wifi_features_df[col].mean()
                            wifi_features[f"{col}_std"] = wifi_features_df[col].std()
                            wifi_features[f"{col}_max"] = wifi_features_df[col].max()
                            wifi_features[f"{col}_min"] = wifi_features_df[col].min()
                
                # Convert WiFi measurements to serializable format
                wifi_measurements_serializable = []
                for measurement in wifi_measurements:
                    measurement_dict = {
                        "timestamp": measurement.timestamp,
                        "ssid": measurement.ssid,
                        "bssid": measurement.bssid,
                        "signal_strength": measurement.signal_strength,
                        "frequency": measurement.frequency,
                        "channel": measurement.channel,
                        "interface": measurement.interface
                    }
                    wifi_measurements_serializable.append(measurement_dict)
                
                # Create labeled data point
                with self.label_lock:
                    current_label = self.current_label
                
                data_point = LabeledDataPoint(
                    timestamp=timestamp,
                    session_id=self.current_session.session_id if self.current_session else "unknown",
                    label=current_label,
                    camera_data=camera_data,
                    wifi_features=wifi_features,
                    wifi_measurements=wifi_measurements_serializable,
                    manual_annotation=""
                )
                
                # Add to buffer
                self.data_points.append(data_point)
                
                # Update statistics
                self.stats["total_samples"] += 1
                if current_label not in self.stats["samples_per_label"]:
                    self.stats["samples_per_label"][current_label] = 0
                self.stats["samples_per_label"][current_label] += 1
                
                # Save periodically to prevent data loss
                if len(self.data_points) >= self.max_buffer_size:
                    self._save_buffer_to_file()
                
                # Collection frequency (2 Hz)
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error in collection loop: {e}")
                time.sleep(1)
    
    def _save_buffer_to_file(self):
        """Save current buffer to file and clear it."""
        if not self.data_points:
            return
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.current_session.session_id}_part_{timestamp_str}.json"
        filepath = self.output_dir / filename
        
        # Convert data points to serializable format
        serializable_data = []
        for dp in self.data_points:
            serializable_data.append(asdict(dp))
        
        # Save to JSON file
        with open(filepath, 'w') as f:
            json.dump(serializable_data, f, indent=2)
        
        logger.info(f"Saved {len(self.data_points)} data points to {filepath}")
        
        # Update session file list
        if self.current_session:
            self.current_session.data_files.append(str(filepath))
        
        # Clear buffer
        self.data_points.clear()
    
    def _save_collected_data(self) -> Optional[str]:
        """Save all collected data to files."""
        if not self.current_session:
            return None
        
        # Save remaining buffer
        self._save_buffer_to_file()
        
        # Save session metadata
        session_file = self.output_dir / f"{self.current_session.session_id}_session.json"
        session_data = {
            "session": asdict(self.current_session),
            "statistics": self.stats,
            "config": self.config
        }
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        # Create CSV file for easy analysis
        csv_file = self._create_csv_export()
        
        logger.info(f"Session data saved to {session_file}")
        return str(csv_file) if csv_file else str(session_file)
    
    def _create_csv_export(self) -> Optional[Path]:
        """Create CSV file with flattened data for ML training."""
        if not self.current_session or not self.current_session.data_files:
            return None
        
        # Load all data files
        all_data_points = []
        for data_file in self.current_session.data_files:
            try:
                with open(data_file, 'r') as f:
                    data = json.load(f)
                    all_data_points.extend(data)
            except Exception as e:
                logger.warning(f"Could not load {data_file}: {e}")
        
        if not all_data_points:
            return None
        
        # Flatten data for CSV
        csv_rows = []
        for dp in all_data_points:
            row = {
                "timestamp": dp["timestamp"],
                "session_id": dp["session_id"],
                "label": dp["label"],
                "manual_annotation": dp["manual_annotation"]
            }
            
            # Add camera features
            camera_data = dp.get("camera_data", {})
            camera_status = camera_data.get("status", {})
            
            row.update({
                "camera_person_visible": camera_status.get("person_visible", False),
                "camera_time_since_last": camera_status.get("time_since_last_person", 0),
                "camera_frame_count": camera_status.get("frame_count", 0)
            })
            
            # Add WiFi features
            wifi_features = dp.get("wifi_features", {})
            row.update(wifi_features)
            
            # Add WiFi measurement statistics
            wifi_measurements = dp.get("wifi_measurements", [])
            if wifi_measurements:
                signal_strengths = [m["signal_strength"] for m in wifi_measurements]
                row.update({
                    "wifi_ap_count": len(wifi_measurements),
                    "wifi_signal_mean": np.mean(signal_strengths) if signal_strengths else 0,
                    "wifi_signal_std": np.std(signal_strengths) if signal_strengths else 0,
                    "wifi_signal_min": np.min(signal_strengths) if signal_strengths else 0,
                    "wifi_signal_max": np.max(signal_strengths) if signal_strengths else 0
                })
            else:
                row.update({
                    "wifi_ap_count": 0,
                    "wifi_signal_mean": 0,
                    "wifi_signal_std": 0,
                    "wifi_signal_min": 0,
                    "wifi_signal_max": 0
                })
            
            csv_rows.append(row)
        
        # Save to CSV
        csv_file = self.output_dir / f"{self.current_session.session_id}.csv"
        df = pd.DataFrame(csv_rows)
        df.to_csv(csv_file, index=False)
        
        logger.info(f"CSV export created: {csv_file} ({len(csv_rows)} rows)")
        return csv_file
    
    def get_status(self) -> Dict[str, Any]:
        """Get current collection status."""
        return {
            "is_collecting": self.is_collecting,
            "current_session": asdict(self.current_session) if self.current_session else None,
            "current_label": self.current_label,
            "statistics": self.stats,
            "buffer_size": len(self.data_points)
        }


class InteractiveCollector:
    """Interactive command-line interface for data collection."""
    
    def __init__(self, config_file: str = "config/config.yaml"):
        """Initialize interactive collector."""
        self.config = self._load_config(config_file)
        self.collector = DataCollector(self.config)
        self.running = False
    
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from file."""
        try:
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Could not load config file {config_file}: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "camera": {
                "device_id": 0,
                "width": 640,
                "height": 480,
                "fps": 30
            },
            "wifi": {
                "rssi": {
                    "interface": "wlan0",
                    "scan_interval": 1.0
                }
            }
        }
    
    def run(self):
        """Run interactive data collection."""
        print("WiFi Sensing Human Presence - Data Collection")
        print("=" * 50)
        
        self.running = True
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        
        try:
            while self.running:
                self._show_menu()
                choice = input("\nEnter choice: ").strip()
                self._handle_choice(choice)
        
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            if self.collector.is_collecting:
                self.collector.stop_collection()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\nReceived shutdown signal...")
        self.running = False
        if self.collector.is_collecting:
            self.collector.stop_collection()
    
    def _show_menu(self):
        """Display main menu."""
        status = self.collector.get_status()
        
        print(f"\n--- Data Collection Status ---")
        print(f"Collecting: {'YES' if status['is_collecting'] else 'NO'}")
        
        if status['current_session']:
            session = status['current_session']
            print(f"Session: {session['session_id']}")
            print(f"Participant: {session['participant_id']}")
            print(f"Current Label: {status['current_label']}")
        
        if status['is_collecting']:
            stats = status['statistics']
            duration = time.time() - stats['start_time']
            print(f"Duration: {duration:.1f}s")
            print(f"Samples: {stats['total_samples']}")
            print(f"Labels: {stats['samples_per_label']}")
        
        print(f"\n--- Available Commands ---")
        if not status['is_collecting']:
            print("1. Start new collection session")
        else:
            print("2. Stop collection")
            print("3. Set label: visible_camera")
            print("4. Set label: behind_wall")
            print("5. Set label: in_room_hidden")
            print("6. Set label: left_area")
            print("7. Set custom label")
        
        print("8. Show status")
        print("9. Exit")
    
    def _handle_choice(self, choice: str):
        """Handle menu choice."""
        try:
            if choice == "1" and not self.collector.is_collecting:
                self._start_collection()
            elif choice == "2" and self.collector.is_collecting:
                self._stop_collection()
            elif choice == "3" and self.collector.is_collecting:
                self.collector.set_current_label("visible_camera")
            elif choice == "4" and self.collector.is_collecting:
                self.collector.set_current_label("behind_wall")
            elif choice == "5" and self.collector.is_collecting:
                self.collector.set_current_label("in_room_hidden")
            elif choice == "6" and self.collector.is_collecting:
                self.collector.set_current_label("left_area")
            elif choice == "7" and self.collector.is_collecting:
                self._set_custom_label()
            elif choice == "8":
                self._show_detailed_status()
            elif choice == "9":
                self.running = False
            else:
                print("Invalid choice or not available in current state")
                
        except Exception as e:
            logger.error(f"Error handling choice {choice}: {e}")
            print(f"Error: {e}")
    
    def _start_collection(self):
        """Start new collection session."""
        print("\n--- New Collection Session ---")
        
        participant_id = input("Participant ID: ").strip()
        scenario = input("Scenario (e.g., 'wall_occlusion', 'free_movement'): ").strip()
        environment = input("Environment (e.g., 'office', 'home', 'lab'): ").strip()
        notes = input("Notes: ").strip()
        
        session_config = {
            "participant_id": participant_id,
            "scenario": scenario,
            "environment": environment,
            "notes": notes
        }
        
        session_id = self.collector.start_collection(session_config)
        
        if session_id:
            print(f"Collection started! Session ID: {session_id}")
            print("Set appropriate labels as you collect data.")
        else:
            print("Failed to start collection")
    
    def _stop_collection(self):
        """Stop collection session."""
        print("Stopping collection...")
        data_file = self.collector.stop_collection()
        
        if data_file:
            print(f"Data saved to: {data_file}")
        else:
            print("No data to save")
    
    def _set_custom_label(self):
        """Set custom label."""
        label = input("Enter custom label: ").strip()
        if label:
            self.collector.set_current_label(label)
        else:
            print("Empty label not set")
    
    def _show_detailed_status(self):
        """Show detailed status information."""
        status = self.collector.get_status()
        print("\n--- Detailed Status ---")
        print(json.dumps(status, indent=2, default=str))


def main():
    """Main entry point for data collection script."""
    parser = argparse.ArgumentParser(description="WiFi sensing data collection")
    parser.add_argument("--config", "-c", default="config/config.yaml",
                       help="Configuration file path")
    parser.add_argument("--output", "-o", default="data/raw",
                       help="Output directory for collected data")
    parser.add_argument("--non-interactive", action="store_true",
                       help="Run in non-interactive mode")
    parser.add_argument("--duration", "-d", type=int, default=60,
                       help="Collection duration in seconds (non-interactive mode)")
    parser.add_argument("--participant", "-p", default="test_participant",
                       help="Participant ID (non-interactive mode)")
    
    args = parser.parse_args()
    
    if args.non_interactive:
        # Non-interactive mode for automated collection
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)
        except:
            config = {
                "camera": {"device_id": 0, "width": 640, "height": 480},
                "wifi": {"rssi": {"interface": "wlan0", "scan_interval": 1.0}}
            }
        
        collector = DataCollector(config, args.output)
        
        session_config = {
            "participant_id": args.participant,
            "scenario": "automated_collection",
            "environment": "unknown",
            "notes": f"Automated collection for {args.duration}s"
        }
        
        session_id = collector.start_collection(session_config)
        
        if session_id:
            print(f"Started automated collection: {session_id}")
            print(f"Collecting for {args.duration} seconds...")
            
            # Set initial label
            collector.set_current_label("unknown")
            
            time.sleep(args.duration)
            
            data_file = collector.stop_collection()
            print(f"Collection complete. Data saved to: {data_file}")
        else:
            print("Failed to start collection")
            sys.exit(1)
    
    else:
        # Interactive mode
        interactive_collector = InteractiveCollector(args.config)
        interactive_collector.run()


if __name__ == "__main__":
    main()