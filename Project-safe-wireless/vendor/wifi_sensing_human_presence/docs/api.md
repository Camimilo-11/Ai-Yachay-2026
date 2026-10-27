# API Reference

> **WiFi Human Detection System - Technical Documentation**

## 🎯 **WiFiRadar Class**

### Core Detection Engine

```python
# Primary API Entry Point
python wifi_radar.py
```

| Method | Description | Parameters |
|--------|-------------|------------|
| `start_scanning()` | Real-time WiFi scanning | Auto-configured |
| `_analyze_signals()` | Signal change analysis | `current_signals`, `baseline_signals` |
| `_update_baseline_gradual()` | Adaptive baseline learning | `new_signals` |

### Configuration Parameters

```python
HUMAN_DETECTION_THRESHOLD = 0.3    # Main detection sensitivity (dBm)
MICRO_MOVEMENT_THRESHOLD = 0.2     # Micro-movement detection (dBm)  
BASELINE_UPDATE_FREQUENCY = 40     # Baseline adaptation rate (scans)
MAX_HUMANS_DETECTED = 5            # Multi-human capacity
```

## 📊 **Detection Output**

### Signal Analysis Structure

```python
{
    'significant_changes': [
        {
            'ssid': 'Dialog 2.4G', 
            'change': 2.8, 
            'abs_change': 2.8, 
            'signal': -69.2
        }
    ],
    'total_energy': 7.0,
    'humans_detected': 3
}
```

### Performance Metrics

| Metric | Specification | Status |
|--------|---------------|--------|
| **Scanning Rate** | 20Hz (50ms intervals) | ✅ Active |
| **Detection Latency** | <100ms response | ✅ Real-time |
| **Network Coverage** | 10+ concurrent | ✅ Monitoring |
| **Sensitivity Range** | 0.2-0.3 dBm | ✅ Optimized |

## 🔧 **Hardware Integration**

### Network Scanning API

```python
# Windows netsh Integration
command = "netsh wlan show profiles"
scan_result = subprocess.run(command, capture_output=True, text=True)

# Signal Processing  
signal_pattern = r"Signal:\s*(\d+)%"
signal_strength = re.search(signal_pattern, network_info)
```

### Supported Hardware

- ✅ **TP-Link USB WiFi Adapters** (AC600, AC1300 series)
- ✅ **Built-in WiFi adapters** (Intel, Realtek chipsets)  
- ✅ **Windows 10/11** netsh command integration

## 👥 **Multi-Human Detection**

### Clustering Algorithm

```python
def apply_clustering_algorithm(significant_changes):
    # Spatial separation of signal changes
    # Temporal correlation analysis
    # Cross-network validation for accuracy
    # Maximum detection limit (5 humans)
    return distinct_human_count
```

### Detection States

```python
DETECTION_STATES = {
    'no_movement': 0,        # <0.2 dBm
    'micro_movement': 1,     # 0.2-0.3 dBm  
    'single_human': 1,       # 0.3+ dBm single network
    'multiple_humans': 2-5,  # Multiple networks >0.3 dBm
    'group_movement': 3-5    # High energy >5.0 dBm total
}
```

---

> **Status:** ✅ Production API - Real-time operation at 20Hz

- `start() -> bool`: Start camera capture and detection
- `stop()`: Stop camera operations
- `get_latest_detection() -> Optional[Dict]`: Get latest detection results
- `get_current_status() -> Dict`: Get current module status
- `visualize_detections(detection_result) -> np.ndarray`: Draw detection results on frame

**Detection Result Format:**
```python
{
    "frame_id": int,
    "timestamp": float,
    "detections": [
        {
            "bbox": (x, y, width, height),
            "confidence": float,
            "center": (x, y),
            "timestamp": float
        }
    ],
    "person_visible": bool,
    "frame": np.ndarray  # OpenCV image
}
```

#### PersonDetector

Low-level person detection using HOG or DNN.

```python
from src.camera import PersonDetector

detector = PersonDetector(
    detection_method="hog",  # or "dnn"
    confidence_threshold=0.5
)

detections = detector.detect_persons(frame)
```

### WiFi Module (`src.wifi`)

The WiFi module handles signal monitoring and feature extraction.

#### WiFiModule

Main class for WiFi sensing operations.

```python
from src.wifi import WiFiModule

config = {
    "rssi": {
        "interface": "wlan0",
        "scan_interval": 1.0,
        "target_ssids": ["MyNetwork"]
    }
}

wifi = WiFiModule(config)
```

**Methods:**

- `start() -> bool`: Start WiFi scanning
- `stop()`: Stop WiFi operations
- `get_current_measurements() -> List[WiFiMeasurement]`: Get latest measurements
- `extract_recent_features(time_window=30.0) -> pd.DataFrame`: Extract features from recent data
- `get_status() -> Dict`: Get module status

#### WiFiMeasurement

Data class for WiFi signal measurements.

```python
@dataclass
class WiFiMeasurement:
    timestamp: float
    ssid: str
    bssid: str
    signal_strength: float  # RSSI in dBm
    frequency: float        # MHz
    channel: int
    interface: str
```

#### WiFiFeatureExtractor

Extract machine learning features from WiFi measurements.

```python
from src.wifi import WiFiFeatureExtractor

extractor = WiFiFeatureExtractor(
    window_size=5.0,  # seconds
    overlap=0.5       # 50% overlap
)

features_df = extractor.extract_features(measurements)
```

**Extracted Features:**
- `rssi_mean`, `rssi_std`, `rssi_var`
- `rssi_min`, `rssi_max`, `rssi_range`
- `rssi_skewness`, `rssi_kurtosis`
- `rssi_slope`, `rssi_volatility`
- `rssi_dominant_freq`, `rssi_spectral_centroid`

### Fusion Module (`src.fusion`)

The fusion module combines camera and WiFi data for presence decisions.

#### DataFusionModule

Main data fusion coordinator.

```python
from src.fusion import DataFusionModule

config = {
    "strategy": "rule_based",  # or "ml"
    "rules": {
        "camera_timeout": 5.0,
        "wifi_change_threshold": 2.0
    }
}

fusion = DataFusionModule(config)
```

**Methods:**

- `start() -> bool`: Start fusion processing
- `stop()`: Stop fusion operations
- `add_camera_data(camera_data: Dict)`: Add camera detection data
- `add_wifi_data(wifi_features: pd.DataFrame, measurements: List)`: Add WiFi data
- `get_latest_result() -> Optional[FusionResult]`: Get latest fusion decision
- `get_status() -> Dict`: Get fusion status

#### FusionResult

Result of data fusion and decision making.

```python
@dataclass
class FusionResult:
    timestamp: float
    presence_state: PresenceState
    confidence: float
    camera_person_visible: bool
    wifi_features_available: bool
    decision_source: str  # "camera", "wifi", or "fusion"
    additional_info: Dict[str, Any]
```

#### PresenceState

Enumeration for possible presence states.

```python
class PresenceState(Enum):
    VISIBLE_CAMERA = "visible_camera"
    BEHIND_WALL = "behind_wall"
    IN_ROOM_HIDDEN = "in_room_hidden"
    LEFT_AREA = "left_area"
    UNKNOWN = "unknown"
```

### ML Module (`src.ml`)

Machine learning pipeline for presence classification.

#### MLPipeline

End-to-end ML training and inference pipeline.

```python
from src.ml import MLPipeline

config = {
    "type": "random_forest",
    "random_forest": {
        "n_estimators": 100,
        "max_depth": 10
    },
    "training": {
        "test_size": 0.2,
        "cross_validation_folds": 5
    }
}

pipeline = MLPipeline(config)
```

**Methods:**

- `train_from_data_files(data_files: List[str]) -> Dict`: Train model from CSV files
- `evaluate_model(model_path: str, test_files: List[str]) -> Dict`: Evaluate trained model

#### ModelTrainer

Core model training functionality.

```python
from src.ml import ModelTrainer

trainer = ModelTrainer(config)
results = trainer.train(
    features_df, 
    labels,
    validate=True,
    tune_hyperparameters=False
)

predictions, probabilities = trainer.predict(new_features_df)
```

**Training Results:**
```python
{
    "training_time": float,
    "test_accuracy": float,
    "cv_mean": float,
    "cv_std": float,
    "confusion_matrix": List[List[int]],
    "classification_report": Dict,
    "model_path": str
}
```

### Utils Module (`src.utils`)

Utility functions for configuration, logging, and data processing.

#### ConfigLoader

Configuration file loading with validation and defaults.

```python
from src.utils import ConfigLoader

loader = ConfigLoader()
config = loader.load_config("config/config.yaml")
loader.save_config(config, "config/output.yaml")
```

#### Data Processing

Functions for processing collected data.

```python
from src.utils import load_session_data, combine_sessions, clean_data

# Load session data
df, metadata = load_session_data("data/raw/session_001_session.json")

# Combine multiple sessions
combined_df = combine_sessions(session_files, "data/processed/combined.csv")

# Clean data
clean_df = clean_data(df, remove_unlabeled=True, min_samples_per_label=10)

# Analyze quality
quality_report = analyze_data_quality(df)

# Export for ML
output_files = export_for_ml(df, output_dir="data/processed")
```

#### Logging

Centralized logging configuration.

```python
from src.utils import setup_logging, get_logger

setup_logging(
    log_level="INFO",
    log_file="logs/app.log",
    rotation="10 MB",
    retention="7 days"
)

logger = get_logger("MyModule")
logger.info("Application started")
```

## Scripts

### Data Collection (`scripts/collect_data.py`)

Interactive and automated data collection.

```bash
# Interactive mode
python scripts/collect_data.py --config config/config.yaml

# Automated mode
python scripts/collect_data.py --non-interactive --duration 300 --participant test_01
```

**Command Line Arguments:**
- `--config`, `-c`: Configuration file path
- `--output`, `-o`: Output directory
- `--non-interactive`: Run without user interaction
- `--duration`, `-d`: Collection duration (seconds)
- `--participant`, `-p`: Participant ID

### Model Training (`scripts/train_model.py`)

Train machine learning models from collected data.

```bash
python scripts/train_model.py \
    --config config/config.yaml \
    --data-dir data/raw \
    --model-type random_forest \
    --tune-hyperparameters
```

**Command Line Arguments:**
- `--config`, `-c`: Configuration file path
- `--data-dir`, `-d`: Directory with session data
- `--output-dir`, `-o`: Output directory for processed data
- `--model-type`, `-m`: Model type (random_forest, svm, neural_network)
- `--tune-hyperparameters`: Perform hyperparameter tuning
- `--validate`: Perform model validation (default: True)

## Main Application (`main.py`)

Primary application entry point.

```bash
# Standard mode with display
python main.py --config config/config.yaml

# Headless mode
python main.py --headless --duration 60

# Debug mode
python main.py --log-level DEBUG
```

**Command Line Arguments:**
- `--config`, `-c`: Configuration file path
- `--headless`: Run without display
- `--duration`, `-d`: Run duration for headless mode
- `--log-level`: Override log level (DEBUG, INFO, WARNING, ERROR)

**Interactive Controls:**
- `q`: Quit application
- `s`: Save screenshot
- `d`: Toggle display

## Configuration Reference

### Complete Configuration Structure

```yaml
camera:
  device_id: 0
  width: 640
  height: 480
  fps: 30
  person_detection:
    confidence_threshold: 0.5
    nms_threshold: 0.4

wifi:
  data_type: "rssi"  # "rssi", "csi", or "both"
  rssi:
    interface: "wlan0"
    scan_interval: 1.0
    target_ssids: []
  csi:
    device_type: "intel5300"  # "intel5300" or "esp32"
    sampling_rate: 20

ml:
  features:
    window_size: 5.0
    overlap: 0.5
    rssi_features:
      - "mean"
      - "std"
      - "variance"
  model:
    type: "random_forest"
    random_forest:
      n_estimators: 100
      max_depth: 10
  training:
    test_size: 0.2
    validation_size: 0.1
    cross_validation_folds: 5

fusion:
  strategy: "rule_based"  # "rule_based" or "ml"
  rules:
    camera_timeout: 5.0
    wifi_change_threshold: 2.0
    min_wifi_samples: 5

data_collection:
  session_duration: 300
  data_dir: "data/raw"
  labels:
    - "visible_camera"
    - "behind_wall"
    - "in_room_hidden"
    - "left_area"

system:
  log_level: "INFO"
  log_file: "logs/wifi_sensing.log"
  save_raw_data: true
  data_retention_days: 30

privacy:
  consent_required: true
  anonymize_data: true
  max_recording_duration: 3600
  delete_video_after_processing: true
```

## Error Handling

### Exception Classes

The system uses standard Python exceptions with descriptive messages. Common exceptions:

- `ValueError`: Invalid configuration or parameters
- `FileNotFoundError`: Missing configuration or data files
- `RuntimeError`: Hardware initialization failures
- `PermissionError`: Insufficient system permissions

### Error Recovery

The system implements graceful error recovery:

- **Camera failures**: Automatic retry and fallback to last known state
- **WiFi scanning issues**: Continued operation with reduced functionality
- **Model errors**: Fallback to rule-based decision making

### Logging

All errors are logged with context information:

```python
logger.error(f"Camera initialization failed: {e}")
logger.warning(f"WiFi scan timeout, using cached data")
logger.debug(f"Processing frame {frame_id} with {len(detections)} detections")
```

## Performance Considerations

### Optimization Guidelines

1. **Camera Settings**: Balance resolution and FPS based on hardware
2. **WiFi Scanning**: Adjust scan intervals based on environment dynamics
3. **Feature Extraction**: Tune window sizes for responsiveness vs. accuracy
4. **Model Selection**: Choose appropriate model complexity for real-time constraints

### Resource Monitoring

```python
# Get system status
status = app.get_status()
print(f"CPU usage: {status['system']['cpu_percent']}%")
print(f"Memory usage: {status['system']['memory_mb']} MB")
print(f"Processing rate: {status['stats']['fps']} FPS")
```

### Scalability

- **Multi-camera support**: Configure multiple camera instances
- **Distributed processing**: Run modules on separate devices
- **Cloud integration**: Stream data to cloud ML services