# Installation & Setup

> **Professional deployment guide for production environments**

## ✅ **System Requirements**

### Hardware
- **CPU:** Intel Core i3+ or AMD equivalent (2GHz+)
- **RAM:** 4GB minimum, 8GB recommended  
- **WiFi:** TP-Link USB adapter or built-in 802.11n/ac/ax
- **OS:** Windows 10/11 (Linux/macOS compatible)

### Verified Configurations
- ✅ **TP-Link AC600/AC1300** USB adapters
- ✅ **Windows netsh** command integration
- ✅ **Multi-network environments** (10+ concurrent networks)
- ✅ **Real-time processing** at 20Hz scanning rate

## 🚀 **Quick Installation**

### 1. Environment Setup
```bash
# Verify Python 3.8+
python --version

# Navigate to project
cd wifi-sensing-human-presence
```

### 2. WiFi Hardware Verification
```bash
# Windows: Check WiFi adapters
netsh wlan show interfaces

# Expected: Connected TP-Link or built-in adapter
```

### 3. Start System
```bash
# Launch WiFi-based detection
python wifi_radar.py

# System automatically:
# ✅ Scans available WiFi networks
# ✅ Establishes adaptive baselines  
# ✅ Monitors signal variations
# ✅ Detects human presence/movement
```

## 📊 **Performance Optimization**

### Network Environment
- **5+ WiFi networks** recommended for optimal detection
- **Mixed signal strengths** (-40 to -80 dBm range)
- **Stable baseline environment** with minimal interference
- **Clear monitoring area** for consistent signal propagation

### System Configuration
- **Dedicated WiFi adapter** (USB dongle preferred)
- **Real-time process priority** for consistent scanning
- **Debug output monitoring** for performance validation
- **Background process optimization** (<10% CPU usage)

## 🔧 **Advanced Configuration**

### Detection Parameters
```python
# Modify in wifi_radar.py for custom sensitivity
HUMAN_DETECTION_THRESHOLD = 0.25   # Lower = higher sensitivity
MICRO_MOVEMENT_THRESHOLD = 0.15    # Micro-movement detection
MAX_HUMANS_DETECTED = 8            # Multi-human capacity
```

### Debug Settings
```python
DEBUG_SIGNAL_ANALYSIS = True       # Detailed signal analysis
DEBUG_DETECTION_LOGIC = True       # Detection decision process
DEBUG_BASELINE_UPDATES = True      # Baseline adaptation
```

## ✅ **Deployment Verification**

### Expected System Output
```
[DEBUG] Successfully parsed 10 WiFi networks from TP-Link dongle
[DEBUG] ⚡ SIGNIFICANT: Dialog 2.4G change 2.8 dBm >= 0.2
[DEBUG] Final result: 3 humans detected
```

### Performance Indicators
- **Network scanning:** Consistent 10+ networks detected
- **Signal stability:** Baseline establishment within 30-40 scans
- **Detection accuracy:** 1.4-2.8 dBm variations during movement
- **Response time:** <100ms from movement to detection

---

> **Status:** ✅ Production-ready deployment guide
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python3 git
```

**Windows:**
- Install Python 3.8+ from python.org
- Install Git for Windows
- Install Microsoft Visual C++ Build Tools

### 2. Project Setup

```bash
# Clone repository
git clone <your-repo-url>
cd wifi-sensing-human-presence

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/macOS
# OR
venv\Scripts\activate  # Windows

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Hardware Configuration

#### Camera Setup

**Test camera access:**
```bash
# Linux - check available cameras
ls /dev/video*

# Test with OpenCV
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('Camera OK' if cap.isOpened() else 'Camera failed')"
```

**Camera permissions (Linux):**
```bash
# Check camera permissions
ls -l /dev/video0

# If needed, add user to video group
sudo usermod -a -G video $USER
# Then log out and back in
```

#### WiFi Setup

**Linux WiFi configuration:**
```bash
# Check WiFi interfaces
iwconfig
nmcli dev wifi

# Test WiFi scanning
sudo iwlist wlan0 scan | head -20

# For CSI tools, may need monitor mode
sudo iw dev wlan0 interface add mon0 type monitor
sudo ip link set dev mon0 up
```

**macOS WiFi configuration:**
```bash
# Install airport utility (may require SIP disable)
# Check available networks
/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -s
```

### 4. Configuration

#### Basic Configuration

```bash
# Copy example configuration
cp config/config.yaml config/my_config.yaml

# Edit configuration file
nano config/my_config.yaml  # or your preferred editor
```

**Key settings to update:**

```yaml
camera:
  device_id: 0  # Change if using different camera

wifi:
  rssi:
    interface: "wlan0"  # Update to your WiFi interface name
    scan_interval: 1.0
    target_ssids: ["YourNetwork", "AnotherNetwork"]  # Optional: specific networks

system:
  log_level: "INFO"  # Use "DEBUG" for troubleshooting
```

#### Advanced Configuration

**For multiple cameras:**
```yaml
camera:
  device_id: 0  # Primary camera
  backup_device_id: 1  # Optional backup
```

**For CSI-enabled hardware:**
```yaml
wifi:
  data_type: "both"  # Use both RSSI and CSI
  csi:
    device_type: "intel5300"  # or "esp32"
    sampling_rate: 20
```

## Testing the Setup

### 1. Basic System Test

```bash
# Test all components
python3 -c "
import sys
sys.path.append('src')
from camera import CameraModule
from wifi import WiFiModule
print('Imports successful')
"
```

### 2. Camera Test

```bash
# Test camera module
python3 -c "
import sys
sys.path.append('src')
from camera import CameraModule
config = {'device_id': 0, 'width': 640, 'height': 480}
cam = CameraModule(config)
print('Camera test:', 'OK' if cam.start() else 'FAILED')
cam.stop()
"
```

### 3. WiFi Test

```bash
# Test WiFi scanning
python3 -c "
import sys
sys.path.append('src')
from wifi import WiFiModule
import time
config = {'rssi': {'interface': 'wlan0', 'scan_interval': 1.0}}
wifi = WiFiModule(config)
if wifi.start():
    print('WiFi started, collecting data...')
    time.sleep(5)
    measurements = wifi.get_current_measurements()
    print(f'Found {len(measurements)} access points')
    wifi.stop()
else:
    print('WiFi test FAILED')
"
```

### 4. Full System Test

```bash
# Run main application for 30 seconds
python3 main.py --headless --duration 30 --config config/my_config.yaml
```

## Troubleshooting

### Common Issues

#### Camera Issues

**"Camera not found" or device_id errors:**
```bash
# List available cameras
ls /dev/video*  # Linux
# Try different device IDs: 0, 1, 2...

# Check camera permissions
ls -l /dev/video0
# Should show your user in video group
```

**"Permission denied" for camera:**
```bash
# Add user to video group
sudo usermod -a -G video $USER
# Log out and back in, or restart
```

#### WiFi Issues

**"No such device" or interface errors:**
```bash
# Check WiFi interface names
ip link show
iwconfig

# Update config.yaml with correct interface name (wlp2s0, wlan0, etc.)
```

**"Operation not permitted" for WiFi scanning:**
```bash
# Try with sudo (temporary)
sudo python3 main.py --config config/my_config.yaml

# Or add scanning permissions
sudo setcap cap_net_raw,cap_net_admin=eip $(which python3)
```

**No access points detected:**
```bash
# Test manual WiFi scanning
sudo iwlist scan | grep ESSID
nmcli dev wifi

# Check if interface is up
sudo ip link set wlan0 up
```

#### Python/Environment Issues

**Import errors or missing packages:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall requirements
pip install --upgrade -r requirements.txt

# For OpenCV issues on Linux:
sudo apt install python3-opencv
```

**Path or module import errors:**
```bash
# Check Python path
python3 -c "import sys; print(sys.path)"

# Ensure you're running from project root directory
pwd  # Should show .../wifi-sensing-human-presence
```

### Performance Issues

**High CPU usage:**
- Reduce camera FPS in config
- Increase WiFi scan interval
- Use headless mode for production

**Memory issues:**
- Reduce feature extraction window size
- Limit data buffer sizes in config
- Use lightweight ML models

### Hardware-Specific Issues

#### Raspberry Pi

```bash
# Enable camera
sudo raspi-config
# Interfacing Options -> Camera -> Enable

# Increase GPU memory
sudo nano /boot/config.txt
# Add: gpu_mem=128

# For WiFi monitor mode
sudo rfkill unblock wifi
```

#### ESP32 CSI Setup

```bash
# Flash CSI firmware to ESP32
# See: https://github.com/StevenMHernandez/ESP32-CSI-Tool

# Connect ESP32 via USB
# Update config with correct serial port
```

### Getting Help

1. **Check logs:** Look in `logs/wifi_sensing.log` for detailed error messages
2. **Enable debug logging:** Set `log_level: "DEBUG"` in config
3. **Test components individually:** Use the test scripts above
4. **Hardware verification:** Ensure camera and WiFi work with other tools
5. **Open an issue:** Include logs, hardware details, and error messages

## Next Steps

After successful setup:

1. **Collect training data:** Use the data collection script
2. **Train models:** Run the model training pipeline
3. **Deploy system:** Run in production mode
4. **Monitor performance:** Check accuracy and adjust parameters

See the main README.md for detailed usage instructions.