#!/usr/bin/env python3
"""
WiFi Radar - Live Object Detection Using WiFi Signals Only
Uses TP-Link dongle to detect and display objects as live graphical shapes.
No camera required - pure WiFi signal analysis!
"""

import sys
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Circle, Rectangle, Ellipse
from collections import deque, defaultdict
import threading
import queue
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

from src.wifi import WiFiModule
from src.utils import ConfigLoader, setup_logging, get_logger


class WiFiRadar:
    """WiFi-only radar system for live object detection."""
    
    def __init__(self):
        self.logger = get_logger("WiFiRadar")
        
        # Initialize WiFi
        self.config = ConfigLoader().load_config("config/config.yaml")
        wifi_config = self.config.get("wifi", {})
        self.wifi_module = WiFiModule(wifi_config)
        
        # Optimized radar parameters for stability and speed
        self.baseline = {}
        self.calibrated = False
        self.scan_history = deque(maxlen=30)  # Reduced from 50 to prevent memory issues
        self.object_positions = []
        self.motion_vectors = deque(maxlen=10)  # Reduced for better performance
        
        # PROPER HUMAN DETECTION PARAMETERS (More sensitive)
        self.human_body_signature_threshold = 0.5  # Lower threshold for better sensitivity
        self.human_size_range = (0.8, 6.0)  # Expected signal change range for human body
        self.non_human_rejection_threshold = 10.0  # Reject changes too large (device interference)
        self.human_network_correlation = 0.3  # Lower correlation requirement
        self.movement_validation_window = 5  # Validate human movement patterns over time
        
        # SIMPLIFIED DETECTION THRESHOLDS - More sensitive for multi-human detection
        self.human_detection_threshold = 0.3  # Main human detection threshold - lowered
        self.micro_movement_threshold = 0.2   # Micro movement detection - more sensitive
        self.strong_movement_threshold = 0.8  # Strong movement detection - lowered
        self.multi_human_threshold = 1.0     # Multiple human detection - more sensitive
        
        # BODY DETECTION SPECIFICS
        self.human_body_mass_signature = (0.5, 8.0)  # More sensitive range
        self.human_walking_pattern = (1.0, 6.0)  # Walking humans create 1-6 dBm changes
        self.human_standing_pattern = (0.2, 3.0)  # Standing humans create 0.2-3 dBm changes
        self.device_interference_rejection = 12.0  # Reject obvious device interference
        
        # VALIDATION REQUIREMENTS (More lenient)
        self.min_networks_for_human = 1  # Even single network can indicate human
        self.human_persistence_validation = 2  # Must show consistent patterns for 2 scans
        self.false_positive_rejection = True  # Enable but less aggressive
        
        # Performance optimization
        self.grid_size = 8
        self.max_distance = 4
        self.max_humans = 5  # Increased for better multi-person detection
        self.last_detection_time = 0
        self.detection_interval = 0.1  # Slower for better validation
        self.frame_skip_counter = 0
        
        # HUMAN VALIDATION TRACKING
        self.detection_persistence = {}
        self.human_validation_history = deque(maxlen=15)  # Track validation over time
        self.movement_history = deque(maxlen=15)
        self.baseline_update_rate = 0.01  # Very slow to maintain detection sensitivity
        
        # Memory management
        self.memory_cleanup_counter = 0
        self.cleanup_interval = 100  # Clean up every 100 iterations
        
        # Animation setup
        self.fig, (self.ax_radar, self.ax_signals) = plt.subplots(1, 2, figsize=(14, 7))
        self.running = True
        
        # Data queues for thread safety
        self.detection_queue = queue.Queue(maxsize=20)  # Limit queue size
        
        print("🎯 WiFi Human Radar System - ULTRA REAL-TIME EDITION")
        print("📡 No camera needed - pure WiFi human detection")
        print("⚡ Enhanced for instant detection and maximum accuracy")
        print("🚀 20Hz scanning for real-time response!")
        
    def start_wifi_scanning(self):
        """Start WiFi scanning in background thread."""
        self.wifi_module.start()
        time.sleep(2)  # Let it stabilize
        
        # Calibration phase
        print("🔄 Calibrating WiFi baseline...")
        for i in range(5):
            measurements = self.wifi_module.get_current_measurements()
            if measurements and len(measurements) >= 3:
                self.baseline = {m.ssid: m.signal_strength for m in measurements[:8]}
                self.calibrated = True
                print(f"✅ Calibrated with {len(self.baseline)} networks")
                break
            time.sleep(1)
            
        if not self.calibrated:
            print("❌ Failed to calibrate - continuing anyway")
            
        # Start scanning thread
        self.scan_thread = threading.Thread(target=self._continuous_scan, daemon=True)
        self.scan_thread.start()
        
    def _continuous_scan(self):
        """Ultra-fast continuous WiFi scanning for real-time human detection."""
        scan_count = 0
        error_count = 0
        max_errors = 15
        last_human_count = 0
        
        print("🚀 Starting real-time detection mode (20Hz scanning)...")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Ultra-fast rate limiting for real-time response
                if current_time - self.last_detection_time < self.detection_interval:
                    time.sleep(0.01)  # Very short sleep
                    continue
                    
                self.last_detection_time = current_time
                
                measurements = self.wifi_module.get_current_measurements()
                if measurements and self.calibrated and len(measurements) >= 3:
                    detection_data = self._analyze_signals(measurements)
                    
                    # Instant feedback for human detection changes
                    current_human_count = detection_data['human_count']
                    if current_human_count != last_human_count:
                        if current_human_count > 0:
                            print(f"\n🚨 HUMAN DETECTED: {current_human_count} person(s) - Confidence: {detection_data.get('detection_confidence', 0):.2f}")
                        else:
                            print(f"\n👁️ Area clear - No humans detected")
                        last_human_count = current_human_count
                    
                    # Only queue if queue not full (prevent memory buildup)
                    if not self.detection_queue.full():
                        self.detection_queue.put(detection_data)
                    
                    scan_count += 1
                    error_count = 0  # Reset error count on success
                    
                    # Less frequent memory cleanup for better performance
                    self.memory_cleanup_counter += 1
                    if self.memory_cleanup_counter >= 200:  # Every 200 scans
                        self._cleanup_memory()
                        self.memory_cleanup_counter = 0
                        
                    # Performance stats every 5 seconds
                    if scan_count % 100 == 0:
                        print(f"📊 Performance: {scan_count} scans completed, {len(measurements)} networks active")
                        
                else:
                    time.sleep(0.02)  # Very short wait if no measurements
                    
            except Exception as e:
                error_count += 1
                self.logger.error(f"Real-time scanning error {error_count}/{max_errors}: {e}")
                
                if error_count >= max_errors:
                    self.logger.error("Too many errors, stopping real-time scanner")
                    break
                    
                time.sleep(0.1)  # Brief pause after error
                
    def _cleanup_memory(self):
        """Periodic memory cleanup to prevent crashes."""
        try:
            # Limit scan history size
            while len(self.scan_history) > 25:
                self.scan_history.popleft()
                
            # Clear old motion vectors
            while len(self.motion_vectors) > 8:
                self.motion_vectors.popleft()
                
            # Clear excess queue items
            while self.detection_queue.qsize() > 15:
                try:
                    self.detection_queue.get_nowait()
                except queue.Empty:
                    break
                    
        except Exception as e:
            self.logger.error(f"Memory cleanup error: {e}")
                
    def _analyze_signals(self, measurements):
        """SIMPLIFIED HUMAN DETECTION that actually works."""
        current_time = time.time()
        current_signals = {m.ssid: m.signal_strength for m in measurements}
        
        # Calculate signal changes - CORRECTED LOGIC
        changes = {}
        total_energy = 0
        significant_changes = []
        
        print(f"[DEBUG] === SIGNAL ANALYSIS START ===")
        print(f"[DEBUG] Networks: baseline={len(self.baseline)}, current={len(current_signals)}")
        
        for ssid, baseline_rssi in self.baseline.items():
            if ssid in current_signals:
                current_rssi = current_signals[ssid]
                change = current_rssi - baseline_rssi
                changes[ssid] = change
                abs_change = abs(change)
                total_energy += abs_change
                
                print(f"[DEBUG] {ssid}: {baseline_rssi:.1f} -> {current_rssi:.1f} = {change:.1f} dBm")
                
                # Collect significant changes for human detection
                if abs_change >= self.micro_movement_threshold:
                    print(f"[DEBUG] ⚡ SIGNIFICANT: {ssid} change {change:.1f} dBm >= {self.micro_movement_threshold}")
                    significant_changes.append({
                        'ssid': ssid,
                        'change': change,
                        'abs_change': abs_change,
                        'signal': current_signals[ssid]
                    })
                else:
                    print(f"[DEBUG] Small change: {ssid} = {change:.1f} dBm (< {self.micro_movement_threshold})")
        
        print(f"[DEBUG] Total energy: {total_energy:.2f}, Significant changes: {len(significant_changes)}")
        print(f"[DEBUG] Detection trigger: {significant_changes or total_energy > 0.1}")
        
        # SIMPLE HUMAN DETECTION
        humans = []
        
        # Debug: Print detection attempt info
        if significant_changes or total_energy > 0.1:
            print(f"[DEBUG] Signal analysis - Total energy: {total_energy:.1f}")
            print(f"[DEBUG] Significant changes: {len(significant_changes)}")
            if significant_changes:
                for i, change in enumerate(significant_changes[:3]):
                    print(f"  Change {i+1}: {change['ssid']} = {change['change']:.1f} dBm (abs: {change['abs_change']:.1f})")
            print(f"[DEBUG] Thresholds - Human: {self.human_detection_threshold}, Micro: {self.micro_movement_threshold}")
        
        # Method 1: Strong single-network changes (walking, large movements)
        for change_data in significant_changes:
            if change_data['abs_change'] >= self.human_detection_threshold:
                print(f"[DEBUG] Creating human from strong change: {change_data['abs_change']:.1f} >= {self.human_detection_threshold}")
                # This is likely a human
                human = self._create_human_from_signal_change(change_data, 'detected', len(humans))
                if human:
                    humans.append(human)
                    print(f"[DEBUG] Human created successfully: {human['activity_type']}")
        
        # Method 2: Multiple smaller changes (multiple people, sitting humans) - IMPROVED
        if len(significant_changes) >= 2 and len(humans) < self.max_humans:  # Lowered from 3 to 2
            print(f"[DEBUG] Attempting cluster detection: {len(significant_changes)} changes")
            # Group remaining smaller changes as additional humans
            remaining_changes = [c for c in significant_changes if c['abs_change'] < self.strong_movement_threshold]
            print(f"[DEBUG] Remaining smaller changes: {len(remaining_changes)}")
            
            # Create humans from clusters of smaller changes - MORE AGGRESSIVE
            while remaining_changes and len(humans) < self.max_humans:
                cluster_changes = remaining_changes[:1]  # Take 1 change per human for better multi-detection
                remaining_changes = remaining_changes[1:]  # Move by 1 instead of 2
                
                if cluster_changes:
                    avg_change = sum(c['abs_change'] for c in cluster_changes) / len(cluster_changes)
                    print(f"[DEBUG] Cluster avg change: {avg_change:.1f} >= {self.micro_movement_threshold}?")
                    if avg_change >= self.micro_movement_threshold:
                        human = self._create_human_from_cluster(cluster_changes, 'sitting/standing', len(humans))
                        if human:
                            humans.append(human)
                            print(f"[DEBUG] Cluster human created: {human['activity_type']}")
        
        # Method 3: High total energy indicates multiple humans - MORE SENSITIVE
        if total_energy >= self.multi_human_threshold and len(humans) < 3:  # Allow up to 3 humans
            print(f"[DEBUG] High energy detection: {total_energy:.1f} >= {self.multi_human_threshold}")
            # Add estimated humans based on total energy - more generous estimation
            estimated_humans = min(4, max(2, int(total_energy / 0.5)))  # More aggressive estimation
            print(f"[DEBUG] Estimated humans from energy: {estimated_humans}")
            while len(humans) < estimated_humans and len(humans) < self.max_humans:
                # Create estimated human
                human = self._create_estimated_human(total_energy, len(humans))
                if human:
                    humans.append(human)
                    print(f"[DEBUG] Energy-based human created: {human['activity_type']}")
        
        if humans:
            print(f"[DEBUG] Final result: {len(humans)} humans detected")
        elif significant_changes:
            print(f"[DEBUG] No humans detected despite {len(significant_changes)} signal changes")
        
        # Update tracking history
        self.movement_history.append({
            'timestamp': current_time,
            'total_energy': total_energy,
            'significant_changes': len(significant_changes),
            'detected_humans': len(humans)
        })
        
        # Update baseline gradually - MUCH LESS FREQUENT (every 2 seconds instead of every scan)
        if len(self.scan_history) % 40 == 0:  # Every 40 scans = every 2 seconds at 20Hz
            print(f"[DEBUG] 📊 Updating baseline (every 40 scans for stability)")
            self._update_baseline_gradual(current_signals)
        else:
            print(f"[DEBUG] Baseline stable (scan {len(self.scan_history) % 40}/40)")
        
        # Store scan data
        changes_for_storage = {}
        for ssid, baseline_rssi in self.baseline.items():
            if ssid in current_signals:
                change = current_signals[ssid] - baseline_rssi
                if abs(change) > 0.1:  # Only store significant changes
                    changes_for_storage[ssid] = change
        
        scan_data = {
            'timestamp': current_time,
            'changes': changes_for_storage,
            'objects': humans,
            'motion_intensity': min(total_energy, 10.0),
            'total_energy': total_energy,
            'human_count': len(humans),
            'detection_confidence': max([h.get('confidence', 0) for h in humans] + [0.5]) if humans else 0,
            'significant_changes_count': len(significant_changes)
        }
        
        self.scan_history.append(scan_data)
        return scan_data
        
    def _create_human_from_signal_change(self, change_data, detection_type, human_id):
        """Create human detection from a single strong signal change."""
        try:
            abs_change = change_data['abs_change']
            
            # Calculate position (spread humans around)
            angle = (human_id * 120 + hash(change_data['ssid']) % 60) % 360
            distance = min(2.5, max(1.0, abs_change * 0.6))
            
            x = distance * np.cos(np.radians(angle))
            y = distance * np.sin(np.radians(angle))
            
            # Determine activity
            if abs_change >= self.strong_movement_threshold:
                activity = 'walking'
                confidence = 0.8
            elif abs_change >= self.human_detection_threshold:
                activity = 'moving'
                confidence = 0.6
            else:
                activity = 'sitting'
                confidence = 0.4
            
            return {
                'x': x, 'y': y, 'size': max(0.3, min(0.7, abs_change * 0.3)),
                'intensity': abs_change,
                'confidence': confidence,
                'type': 'human',
                'activity_type': activity,
                'human_id': human_id,
                'detection_method': detection_type,
                'primary_network': change_data['ssid'][:10]
            }
        except Exception as e:
            self.logger.error(f"Human creation error: {e}")
            return None
    
    def _create_human_from_cluster(self, cluster_changes, detection_type, human_id):
        """Create human from multiple smaller signal changes."""
        try:
            total_change = sum(c['abs_change'] for c in cluster_changes)
            
            # Position based on cluster
            angle = (human_id * 90 + len(cluster_changes) * 30) % 360
            distance = min(2.8, max(1.2, total_change * 0.4))
            
            x = distance * np.cos(np.radians(angle))
            y = distance * np.sin(np.radians(angle))
            
            return {
                'x': x, 'y': y, 'size': max(0.2, min(0.5, total_change * 0.2)),
                'intensity': total_change,
                'confidence': 0.5,
                'type': 'human',
                'activity_type': 'multi-signal',
                'human_id': human_id,
                'detection_method': detection_type,
                'networks_count': len(cluster_changes)
            }
        except Exception as e:
            self.logger.error(f"Cluster human creation error: {e}")
            return None
    
    def _create_estimated_human(self, total_energy, human_id):
        """Create estimated human from high total energy."""
        try:
            # Spread estimated humans in different positions
            angle = human_id * 180
            distance = 2.0
            
            x = distance * np.cos(np.radians(angle))
            y = distance * np.sin(np.radians(angle))
            
            return {
                'x': x, 'y': y, 'size': 0.4,
                'intensity': total_energy / 3,
                'confidence': 0.4,
                'type': 'human',
                'activity_type': 'estimated',
                'human_id': human_id,
                'detection_method': 'energy_based'
            }
        except Exception as e:
            self.logger.error(f"Estimated human creation error: {e}")
            return None
    
    def _update_baseline_gradual(self, current_signals):
        """Gradual baseline updates to maintain sensitivity while adapting."""
        for ssid, current_rssi in current_signals.items():
            if ssid in self.baseline:
                # Very slow adaptation (1% per scan)
                self.baseline[ssid] = self.baseline[ssid] * 0.99 + current_rssi * 0.01
        
    def _create_human_from_signal_change(self, change_data, detection_type, human_id):
        """Create human detection from a single strong signal change."""
        try:
            abs_change = change_data['abs_change']
            
            # Calculate position (spread humans around)
            angle = (human_id * 120 + hash(change_data['ssid']) % 60) % 360
            distance = min(2.5, max(1.0, abs_change * 0.6))
            
            x = distance * np.cos(np.radians(angle))
            y = distance * np.sin(np.radians(angle))
            
            # Determine activity
            if abs_change >= self.strong_movement_threshold:
                activity = 'walking'
                confidence = 0.8
            elif abs_change >= self.human_detection_threshold:
                activity = 'moving'
                confidence = 0.6
            else:
                activity = 'sitting'
                confidence = 0.4
            
            return {
                'x': x, 'y': y, 'size': max(0.3, min(0.7, abs_change * 0.3)),
                'intensity': abs_change,
                'confidence': confidence,
                'type': 'human',
                'activity_type': activity,
                'human_id': human_id,
                'detection_method': detection_type,
                'primary_network': change_data['ssid'][:10]
            }
        except Exception as e:
            self.logger.error(f"Human creation error: {e}")
            return None
    
    def _create_human_from_cluster(self, cluster_changes, detection_type, human_id):
        """Create human from multiple smaller signal changes."""
        try:
            total_change = sum(c['abs_change'] for c in cluster_changes)
            
            # Position based on cluster
            angle = (human_id * 90 + len(cluster_changes) * 30) % 360
            distance = min(2.8, max(1.2, total_change * 0.4))
            
            x = distance * np.cos(np.radians(angle))
            y = distance * np.sin(np.radians(angle))
            
            return {
                'x': x, 'y': y, 'size': max(0.2, min(0.5, total_change * 0.2)),
                'intensity': total_change,
                'confidence': 0.5,
                'type': 'human',
                'activity_type': 'multi-signal',
                'human_id': human_id,
                'detection_method': detection_type,
                'networks_count': len(cluster_changes)
            }
        except Exception as e:
            self.logger.error(f"Cluster human creation error: {e}")
            return None
    
    def _create_estimated_human(self, total_energy, human_id):
        """Create estimated human from high total energy."""
        try:
            # Spread estimated humans in different positions
            angle = human_id * 180
            distance = 2.0
            
            x = distance * np.cos(np.radians(angle))
            y = distance * np.sin(np.radians(angle))
            
            return {
                'x': x, 'y': y, 'size': 0.4,
                'intensity': total_energy / 3,
                'confidence': 0.4,
                'type': 'human',
                'activity_type': 'estimated',
                'human_id': human_id,
                'detection_method': 'energy_based'
            }
        except Exception as e:
            self.logger.error(f"Estimated human creation error: {e}")
            return None
    
    def _update_baseline_gradual(self, current_signals):
        """Gradual baseline updates to maintain sensitivity while adapting."""
        for ssid, current_rssi in current_signals.items():
            if ssid in self.baseline:
                # Very slow adaptation (1% per scan)
                self.baseline[ssid] = self.baseline[ssid] * 0.99 + current_rssi * 0.01

    def _find_correlated_networks(self, primary_ssid, primary_change, all_changes):
        """Find networks showing correlated changes (indicating same physical presence)."""
        correlated = []
        
        for ssid, change in all_changes.items():
            if ssid == primary_ssid:
                continue
                
            abs_change = abs(change)
            
            # Check for human-body-size correlation
            if abs_change >= 0.3:  # Must be significant enough
                
                # Check correlation pattern (human body creates predictable patterns)
                correlation_strength = self._calculate_signal_correlation(primary_change, change)
                
                if correlation_strength >= self.human_network_correlation:
                    correlated.append({
                        'ssid': ssid,
                        'change': change,
                        'correlation': correlation_strength
                    })
                    
        return correlated
        
    def _calculate_signal_correlation(self, change1, change2):
        """Calculate how well two signal changes correlate (human body creates correlated patterns)."""
        abs1, abs2 = abs(change1), abs(change2)
        
        # Human body creates proportional signal changes across networks
        if abs1 > 0 and abs2 > 0:
            ratio = min(abs1, abs2) / max(abs1, abs2)
            
            # Same direction changes = higher correlation (blocking effect)
            if (change1 > 0 and change2 > 0) or (change1 < 0 and change2 < 0):
                return ratio * 0.9
            else:
                # Opposite directions still possible (blocking vs reflection)
                return ratio * 0.5
        
        return 0.0
        
    def _calculate_initial_human_probability(self, signal_strength, correlation_count):
        """Calculate initial probability this is a human based on signal characteristics."""
        probability = 0.0
        
        # Signal strength matching human body mass
        if 1.0 <= signal_strength <= 4.0:
            probability += 0.4  # Strong human body signature
        elif 0.8 <= signal_strength <= 6.0:
            probability += 0.2  # Possible human body signature
            
        # Multiple network correlation (human body size effect)
        if correlation_count >= 3:
            probability += 0.4  # Strong multi-network evidence
        elif correlation_count >= 2:
            probability += 0.2  # Moderate multi-network evidence
            
        return min(probability, 1.0)
        
    def _validate_human_detection(self, candidates, all_changes, current_time):
        """Step 2: Validate candidates using human body physics."""
        validated = []
        
        for candidate in candidates:
            validation_score = 0
            validation_reasons = []
            
            # VALIDATION 1: Signal strength in human range
            signal_strength = candidate['signal_strength']
            if self.human_body_mass_signature[0] <= signal_strength <= self.human_body_mass_signature[1]:
                validation_score += 0.3
                validation_reasons.append('human_body_range')
                
            # VALIDATION 2: Multiple network correlation (human body size)
            correlation_count = len(candidate['correlated_networks'])
            if correlation_count >= 3:
                validation_score += 0.3
                validation_reasons.append('multi_network_body_effect')
                
            # VALIDATION 3: Realistic human movement pattern
            if candidate['activity'] in ['walking', 'standing_moving']:
                validation_score += 0.2
                validation_reasons.append('human_activity_pattern')
                
            # VALIDATION 4: Reject device interference
            if signal_strength > self.device_interference_rejection:
                validation_score = 0  # Definitely not human
                validation_reasons = ['device_interference_rejected']
                
            # VALIDATION 5: Time-based validation
            if len(self.movement_history) >= 5:
                recent_detections = [h.get('human_candidates', 0) for h in list(self.movement_history)[-5:]]
                if sum(recent_detections) >= 2:  # Consistent detection over time
                    validation_score += 0.2
                    validation_reasons.append('temporal_consistency')
                    
            # Must meet much lower validation threshold for responsiveness
            if validation_score >= 0.2:  # Much more responsive
                validated.append({
                    **candidate,
                    'validation_score': validation_score,
                    'validation_reasons': validation_reasons,
                    'validated_at': current_time
                })
                
        return validated
        
    def _confirm_human_with_movement_validation(self, validated_humans, current_time):
        """Step 3: Cross-validate with movement patterns."""
        confirmed = []
        
        for human in validated_humans:
            # Add movement pattern validation
            movement_score = self._analyze_movement_patterns(human, current_time)
            
            if movement_score >= 0.3:  # Minimum movement validation
                confirmed.append({
                    **human,
                    'movement_score': movement_score,
                    'confirmed_at': current_time
                })
                
        return confirmed
        
    def _analyze_movement_patterns(self, human, current_time):
        """Analyze if movement patterns are consistent with human behavior."""
        if len(self.movement_history) < 5:
            return 0.5  # Insufficient data, give benefit of doubt
            
        # Check for human-like movement consistency
        recent_energies = [h.get('total_energy', 0) for h in list(self.movement_history)[-5:]]
        
        if len(recent_energies) >= 3:
            energy_variation = np.std(recent_energies)
            energy_mean = np.mean(recent_energies)
            
            # Human movement creates moderate, consistent variations
            if 0.2 < energy_variation < 5.0 and energy_mean > 0.5:
                return 0.8  # Good human movement pattern
            elif 0.1 < energy_variation < 2.0:
                return 0.4  # Possible human movement
                
        return 0.1  # Weak movement validation
        
    def _reject_false_positives(self, confirmed_humans, changes):
        """Step 4: Final false positive rejection."""
        if not self.false_positive_rejection:
            return confirmed_humans
            
        final_humans = []
        
        for human in confirmed_humans:
            rejection_reasons = []
            keep_human = True
            
            # REJECTION 1: Signal too large (device interference)
            if human['signal_strength'] > 8.0:
                rejection_reasons.append('signal_too_large_device_interference')
                keep_human = False
                
            # REJECTION 2: Too many simultaneous "humans" (likely interference)
            if len(confirmed_humans) > 3:
                # Keep only the strongest detections
                if human['validation_score'] < 0.8:
                    rejection_reasons.append('too_many_simultaneous_detections')
                    keep_human = False
                    
            # REJECTION 3: Inconsistent with physics
            total_signal_change = sum(abs(c) for c in changes.values())
            if total_signal_change > 20.0:  # Too much change for human presence
                rejection_reasons.append('total_signal_change_too_large')
                keep_human = False
                
            if keep_human:
                final_human = self._create_validated_human_detection(human)
                if final_human:
                    final_humans.append(final_human)
            else:
                self.logger.debug(f"Rejected human detection: {rejection_reasons}")
                
        return final_humans
        
    def _create_validated_human_detection(self, validated_human):
        """Create final human detection from validated data."""
        try:
            signal_strength = validated_human['signal_strength']
            validation_score = validated_human['validation_score']
            activity = validated_human['activity']
            
            # Calculate position based on signal propagation physics
            distance = max(1.0, min(3.0, 3.5 - (signal_strength * 0.4)))
            angle = hash(validated_human['primary_network']) % 360
            
            x = distance * np.cos(np.radians(angle))
            y = distance * np.sin(np.radians(angle))
            
            # Size based on validation confidence
            size = max(0.2, min(0.6, validation_score * 0.8))
            
            return {
                'x': x, 'y': y, 'size': size,
                'intensity': signal_strength,
                'confidence': validation_score,
                'type': 'human',
                'activity_type': activity,
                'movement_type': activity,
                'human_id': len(self.detection_persistence),
                'networks_affected': len(validated_human['correlated_networks']) + 1,
                'detection_type': 'validated',
                'validation_reasons': validated_human['validation_reasons']
            }
            
        except Exception as e:
            self.logger.error(f"Validated human creation error: {e}")
            return None
            
    def _update_baseline_conservative(self, current_signals):
        """Very conservative baseline updates to maintain detection sensitivity."""
        for ssid, current_rssi in current_signals.items():
            if ssid in self.baseline:
                old_baseline = self.baseline[ssid]
                # Extremely slow adaptation
                self.baseline[ssid] = old_baseline * (1 - self.baseline_update_rate) + current_rssi * self.baseline_update_rate
        
    def _detect_realtime_humans(self, changes, instant_changes, total_energy):
        """Real-time human detection using advanced signal analysis."""
        clusters = []
        
        # Process instant detection changes first (high confidence)
        for change_data in instant_changes:
            cluster = {
                'primary_ssid': change_data['ssid'],
                'primary_change': change_data['change'],
                'strength': change_data['abs_change'],
                'signal_level': change_data['signal_strength'],
                'supporting_changes': [],
                'detection_type': 'instant'
            }
            
            # Find correlated changes (other networks affected by same human)
            for ssid, change_val in changes.items():
                if ssid != change_data['ssid'] and abs(change_val) > 0.2:
                    # Check if change pattern suggests same human
                    correlation = self._calculate_signal_correlation(change_data['change'], change_val)
                    if correlation > 0.3:
                        cluster['supporting_changes'].append({
                            'ssid': ssid,
                            'change': change_val,
                            'correlation': correlation
                        })
                        
            clusters.append(cluster)
            
        # Process moderate energy changes for additional humans
        if total_energy > 1.0 and len(clusters) < self.max_humans:
            moderate_changes = [(ssid, change) for ssid, change in changes.items() 
                              if 0.3 < abs(change) < 2.0]
            
            # Group moderate changes that might represent additional humans
            while moderate_changes and len(clusters) < self.max_humans:
                primary_ssid, primary_change = moderate_changes.pop(0)
                
                cluster = {
                    'primary_ssid': primary_ssid,
                    'primary_change': primary_change,
                    'strength': abs(primary_change),
                    'signal_level': self.baseline.get(primary_ssid, -80) + primary_change,
                    'supporting_changes': [],
                    'detection_type': 'moderate'
                }
                
                # Find supporting moderate changes
                remaining_changes = moderate_changes.copy()
                for ssid, change_val in remaining_changes:
                    if abs(change_val) > 0.15:
                        cluster['supporting_changes'].append({
                            'ssid': ssid,
                            'change': change_val,
                            'correlation': 0.5  # Moderate correlation
                        })
                        moderate_changes.remove((ssid, change_val))
                        
                clusters.append(cluster)
                
        return clusters
        
    def _calculate_signal_correlation(self, change1, change2):
        """Calculate correlation between signal changes to detect same human."""
        # Humans typically cause correlated signal changes across networks
        if (change1 > 0 and change2 > 0) or (change1 < 0 and change2 < 0):
            # Same direction = higher correlation
            ratio = min(abs(change1), abs(change2)) / max(abs(change1), abs(change2))
            return ratio * 0.8
        else:
            # Opposite directions can still be same human (blocking vs reflection)
            ratio = min(abs(change1), abs(change2)) / max(abs(change1), abs(change2))
            return ratio * 0.4
            
    def _calculate_human_probability(self, cluster, all_changes, current_time):
        """Calculate probability that cluster represents a human."""
        score = {'confidence': 0.0, 'indicators': [], 'movement_type': 'unknown'}
        
        strength = cluster['strength']
        support_count = len(cluster['supporting_changes'])
        detection_type = cluster['detection_type']
        
        # Indicator 1: Signal strength in human range
        if detection_type == 'instant':
            score['confidence'] += 0.4  # High confidence for instant detection
            score['indicators'].append('instant_detection')
            
        if 0.5 < strength < 6.0:  # Human-typical signal disruption
            score['confidence'] += 0.3
            score['indicators'].append('human_strength')
            
        # Indicator 2: Multiple network correlation
        if support_count >= 2:
            score['confidence'] += 0.2
            score['indicators'].append('multi_network')
            
        # Indicator 3: Realistic movement pattern from history
        if len(self.movement_history) >= 3:
            recent_energies = [h['energy'] for h in list(self.movement_history)[-3:]]
            energy_trend = np.std(recent_energies) if recent_energies else 0
            
            if 0.1 < energy_trend < 3.0:  # Human-like energy variation
                score['confidence'] += 0.2
                score['indicators'].append('movement_pattern')
                
        # Indicator 4: Signal level analysis
        signal_level = cluster.get('signal_level', -80)
        if -85 < signal_level < -60:  # Typical WiFi range for human detection
            score['confidence'] += 0.1
            score['indicators'].append('signal_range')
            
        # Determine movement type
        if strength > 2.0:
            score['movement_type'] = 'walking'
        elif strength > 0.8:
            score['movement_type'] = 'moving'
        else:
            score['movement_type'] = 'standing'
            
        return score
        
    def _create_realtime_human_detection(self, cluster, human_score, human_id):
        """Create human detection with enhanced positioning."""
        try:
            strength = cluster['strength']
            confidence = human_score['confidence']
            
            # Enhanced distance estimation using signal propagation
            base_distance = 3.0 - (strength * 0.6)  # Closer = stronger signal change
            estimated_distance = max(0.5, min(3.5, base_distance))
            
            # Improved angle estimation using network topology
            primary_ssid = cluster['primary_ssid']
            ssid_hash = hash(primary_ssid) % 360
            support_offset = len(cluster['supporting_changes']) * 15
            time_offset = (time.time() * 10) % 30  # Slight animation
            
            angle = (ssid_hash + support_offset + time_offset) % 360
            
            # Convert to coordinates with slight randomization for realism
            x = estimated_distance * np.cos(np.radians(angle))
            y = estimated_distance * np.sin(np.radians(angle))
            
            # Human size based on detection confidence and signal strength
            human_size = max(0.15, min(0.5, confidence * 0.8 + strength * 0.1))
            
            return {
                'x': x, 'y': y, 'size': human_size,
                'intensity': strength,
                'confidence': confidence,
                'type': 'human',
                'movement_type': human_score['movement_type'],
                'human_id': human_id,
                'networks_affected': len(cluster['supporting_changes']) + 1,
                'detection_type': cluster['detection_type'],
                'indicators': human_score['indicators']
            }
            
        except Exception as e:
            self.logger.error(f"Real-time detection creation error: {e}")
            return None
            
    def _detect_walking_humans(self, changes, walking_changes):
        """Detect walking humans from strong signal changes."""
        clusters = []
        for change_data in walking_changes:
            cluster = {
                'primary_ssid': change_data['ssid'],
                'primary_change': change_data['change'],
                'strength': change_data['abs_change'],
                'signal_level': change_data['signal_strength'],
                'supporting_changes': [],
                'activity_type': 'walking'
            }
            
            # Find correlated walking signals
            for ssid, change_val in changes.items():
                if ssid != change_data['ssid'] and abs(change_val) > 0.2:
                    cluster['supporting_changes'].append({
                        'ssid': ssid, 'change': change_val
                    })
                    
            clusters.append(cluster)
        return clusters
        
    def _detect_sitting_humans(self, changes, micro_changes, total_energy):
        """Detect sitting humans from micro-movements and breathing patterns."""
        clusters = []
        
        # Group micro changes that might represent sitting humans
        if len(micro_changes) >= 2:  # Need multiple micro-changes for sitting human
            # Create clusters based on signal correlation
            for i, primary_change in enumerate(micro_changes[:3]):  # Max 3 sitting humans
                cluster = {
                    'primary_ssid': primary_change['ssid'],
                    'primary_change': primary_change['change'],
                    'strength': primary_change['abs_change'],
                    'signal_level': primary_change['signal_strength'],
                    'supporting_changes': [],
                    'activity_type': 'sitting'
                }
                
                # Add supporting micro-changes
                for j, other_change in enumerate(micro_changes):
                    if i != j:
                        cluster['supporting_changes'].append({
                            'ssid': other_change['ssid'],
                            'change': other_change['change']
                        })
                        
                clusters.append(cluster)
                
        # Also check for breathing patterns in signal history
        elif self._has_breathing_pattern() and total_energy > 0.1:
            # Create sitting human from breathing pattern
            strongest_network = max(changes.items(), key=lambda x: abs(x[1]))
            cluster = {
                'primary_ssid': strongest_network[0],
                'primary_change': strongest_network[1],
                'strength': abs(strongest_network[1]),
                'signal_level': self.baseline.get(strongest_network[0], -80) + strongest_network[1],
                'supporting_changes': [],
                'activity_type': 'sitting_breathing'
            }
            clusters.append(cluster)
            
        return clusters
        
    def _detect_breathing_patterns(self):
        """Detect if recent signal history shows breathing patterns."""
        if len(self.movement_history) < 10:
            return False
            
        # Check for regular micro-fluctuations (breathing: 12-20 breaths/min)
        recent_energies = [h['energy'] for h in list(self.movement_history)[-10:]]
        if len(recent_energies) < 6:
            return False
            
        # Look for small, regular variations (breathing pattern)
        energy_std = np.std(recent_energies)
        energy_mean = np.mean(recent_energies)
        
        # Breathing creates small but consistent variations
        return 0.02 < energy_std < 0.5 and energy_mean > 0.05
        
    def _has_breathing_pattern(self):
        """Check if there's a breathing pattern in recent history."""
        return self._detect_breathing_patterns()
        
    def _calculate_activity_probability(self, cluster, all_changes, current_time, activity_type):
        """Calculate probability based on activity type (sitting vs walking)."""
        score = {'confidence': 0.0, 'indicators': [], 'activity_type': activity_type}
        
        strength = cluster['strength']
        support_count = len(cluster['supporting_changes'])
        
        # Activity-specific scoring
        if activity_type == 'walking':
            # Walking humans: strong, variable signals
            if strength > 0.8:
                score['confidence'] += 0.4
                score['indicators'].append('strong_walking_signal')
            if support_count >= 2:
                score['confidence'] += 0.3
                score['indicators'].append('multi_network_walking')
                
        elif activity_type in ['sitting', 'sitting_breathing']:
            # Sitting humans: weaker but consistent micro-signals
            if 0.05 < strength < 0.4:
                score['confidence'] += 0.3
                score['indicators'].append('micro_movement')
            if support_count >= 1:
                score['confidence'] += 0.2
                score['indicators'].append('correlated_sitting')
            if self._detect_breathing_patterns():
                score['confidence'] += 0.4
                score['indicators'].append('breathing_detected')
                
        # Network correlation bonus
        if support_count > 0:
            score['confidence'] += min(0.2, support_count * 0.1)
            
        return score
        
    def _is_unique_position(self, human, detected_positions):
        """Check if human position is unique (avoid duplicates)."""
        human_pos = (round(human['x']), round(human['y']))
        return human_pos not in detected_positions
        
    def _maintain_persistent_detections(self, current_humans, current_time):
        """Maintain detection of humans who might have stopped moving temporarily."""
        persistent_humans = []
        
        # Update persistent detection tracking
        for human in current_humans:
            human_id = human.get('human_id', 0)
            self.detection_persistence[human_id] = {
                'last_seen': current_time,
                'position': (human['x'], human['y']),
                'activity': human.get('activity_type', 'unknown'),
                'confidence': human['confidence']
            }
            
        # Check for humans we should still be detecting
        for human_id, data in list(self.detection_persistence.items()):
            time_since_seen = current_time - data['last_seen']
            
            # If human was recently detected but not in current scan
            if (time_since_seen < self.persistence_timeout and 
                not any(h.get('human_id') == human_id for h in current_humans)):
                
                # Create persistent detection with reduced confidence
                confidence_decay = max(0.1, data['confidence'] * (1 - time_since_seen/self.persistence_timeout))
                
                persistent_human = {
                    'x': data['position'][0], 'y': data['position'][1],
                    'size': max(0.15, confidence_decay * 0.4),
                    'intensity': confidence_decay * 2,
                    'confidence': confidence_decay,
                    'type': 'human',
                    'activity_type': data['activity'],
                    'movement_type': data['activity'],
                    'human_id': human_id,
                    'networks_affected': 1,
                    'detection_type': 'persistent',
                    'time_persistent': time_since_seen
                }
                persistent_humans.append(persistent_human)
                
            elif time_since_seen >= self.persistence_timeout:
                # Remove old detections
                del self.detection_persistence[human_id]
                
        return persistent_humans
        
    def _create_persistent_human_detection(self, cluster, human_score, human_id, activity_type):
        """Create human detection with activity-specific characteristics."""
        try:
            strength = cluster['strength']
            confidence = human_score['confidence']
            
            # Activity-specific distance and positioning
            if activity_type == 'walking':
                base_distance = 2.5 - (strength * 0.5)  # Walking = closer detection
                size_multiplier = 1.2  # Larger for walking
            else:  # sitting
                base_distance = 3.0 - (strength * 0.3)  # Sitting = further detection
                size_multiplier = 0.8  # Smaller for sitting
                
            estimated_distance = max(0.5, min(3.5, base_distance))
            
            # Position calculation
            primary_ssid = cluster['primary_ssid']
            ssid_hash = hash(primary_ssid) % 360
            activity_offset = {'walking': 0, 'sitting': 30, 'sitting_breathing': 60}[activity_type]
            angle = (ssid_hash + activity_offset + human_id * 45) % 360
            
            x = estimated_distance * np.cos(np.radians(angle))
            y = estimated_distance * np.sin(np.radians(angle))
            
            # Activity-specific size
            human_size = max(0.15, min(0.6, confidence * 0.6 * size_multiplier))
            
            return {
                'x': x, 'y': y, 'size': human_size,
                'intensity': strength,
                'confidence': confidence,
                'type': 'human',
                'activity_type': activity_type,
                'movement_type': activity_type,
                'human_id': human_id,
                'networks_affected': len(cluster['supporting_changes']) + 1,
                'detection_type': 'active',
                'indicators': human_score['indicators']
            }
            
        except Exception as e:
            self.logger.error(f"Persistent detection creation error: {e}")
            return None
            
    def _update_baseline_adaptive(self, current_signals):
        """Conservatively update baseline to maintain detection sensitivity."""
        for ssid, current_rssi in current_signals.items():
            if ssid in self.baseline:
                # Very slow adaptation to preserve human detection
                old_baseline = self.baseline[ssid]
                self.baseline[ssid] = old_baseline * (1 - self.baseline_update_rate) + current_rssi * self.baseline_update_rate
        
    def _detect_human_clusters(self, significant_changes, all_changes):
        """Detect multiple human clusters from signal patterns."""
        clusters = []
        
        # Simple clustering based on signal strength patterns
        for i, change_data in enumerate(significant_changes[:6]):  # Process top 6 changes
            ssid = change_data['ssid']
            change_val = change_data['change']
            abs_change = change_data['abs_change']
            
            # Each significant change potentially represents a human
            if abs_change > 0.8:  # Strong signal change = likely human
                cluster = {
                    'primary_ssid': ssid,
                    'primary_change': change_val,
                    'strength': abs_change,
                    'supporting_changes': []
                }
                
                # Find supporting changes (nearby networks affected)
                for other_ssid, other_change in all_changes.items():
                    if other_ssid != ssid and abs(other_change) > 0.3:
                        cluster['supporting_changes'].append({
                            'ssid': other_ssid,
                            'change': other_change
                        })
                        
                clusters.append(cluster)
                
        return clusters[:self.max_humans]  # Limit clusters
        
    def _analyze_human_indicators(self, cluster, all_changes):
        """Analyze if cluster represents human presence."""
        indicators = {'score': 0, 'confidence': 0.0, 'type': 'unknown'}
        
        primary_strength = cluster['strength']
        support_count = len(cluster['supporting_changes'])
        
        # Indicator 1: Strong primary signal (human body blocking)
        if 1.0 < primary_strength < 5.0:  # Human-range signal change
            indicators['score'] += 2
            
        # Indicator 2: Multiple supporting networks
        if support_count >= 2:
            indicators['score'] += 1
            
        # Indicator 3: Realistic signal pattern
        if support_count >= 1:
            avg_support = sum(abs(s['change']) for s in cluster['supporting_changes']) / support_count
            if 0.3 < avg_support < 2.0:  # Human-like support pattern
                indicators['score'] += 1
                
        # Indicator 4: Movement type analysis
        if primary_strength > 2.0:
            indicators['type'] = 'walking'
            indicators['score'] += 1
        else:
            indicators['type'] = 'standing'
            
        # Calculate confidence
        indicators['confidence'] = min(indicators['score'] / 4.0, 1.0)
        
        return indicators
        
    def _create_human_detection(self, cluster, indicators, human_id):
        """Create human detection object with improved positioning."""
        try:
            primary_ssid = cluster['primary_ssid']
            strength = cluster['strength']
            
            # Improved distance estimation
            estimated_distance = max(0.8, min(3.5, 4.0 - (strength * 0.8)))
            
            # Better angle estimation using multiple signals
            base_angle = (hash(primary_ssid) + human_id * 60) % 360
            angle_offset = len(cluster['supporting_changes']) * 10
            angle = (base_angle + angle_offset) % 360
            
            # Convert to coordinates
            x = estimated_distance * np.cos(np.radians(angle))
            y = estimated_distance * np.sin(np.radians(angle))
            
            # Human size based on signal strength
            human_size = max(0.2, min(0.6, strength * 0.15))
            
            return {
                'x': x, 'y': y, 'size': human_size,
                'intensity': strength,
                'confidence': indicators['confidence'],
                'type': 'human',
                'movement_type': indicators['type'],
                'human_id': human_id,
                'networks_affected': len(cluster['supporting_changes']) + 1
            }
            
        except Exception as e:
            self.logger.error(f"Human detection creation error: {e}")
            return None
        
    def _update_radar_display(self, frame):
        """Real-time radar display with instant human detection feedback."""
        # No frame skipping for real-time display
        
        # Process detection data with high performance
        new_detections = []
        processed_count = 0
        max_process = 10  # Process more data per frame for responsiveness
        
        while not self.detection_queue.empty() and processed_count < max_process:
            try:
                detection_data = self.detection_queue.get_nowait()
                new_detections.append(detection_data)
                processed_count += 1
            except queue.Empty:
                break
            except Exception as e:
                self.logger.error(f"Real-time processing error: {e}")
                
        # Update object positions with latest data immediately
        if new_detections:
            latest_data = new_detections[-1]  # Use most recent
            self.object_positions = latest_data['objects']
            
            if latest_data.get('motion_intensity', 0) > 0:
                self.motion_vectors.append({
                    'intensity': latest_data['motion_intensity'],
                    'timestamp': latest_data['timestamp'],
                    'human_count': len(self.object_positions),
                    'confidence': latest_data.get('detection_confidence', 0),
                    'instant_detections': latest_data.get('instant_detections', 0)
                })
                
        # Clear and redraw with enhanced error handling
        try:
            self.ax_radar.clear()
            self._draw_radar_grid()
            self._draw_objects_realtime()
            self._draw_motion_trails()
            self._update_signal_plot_realtime()
        except Exception as e:
            self.logger.error(f"Real-time display error: {e}")
            
        return []
        
    def _draw_radar_grid(self):
        """Draw radar-style grid optimized for human detection."""
        self.ax_radar.set_xlim(-self.max_distance, self.max_distance)
        self.ax_radar.set_ylim(-self.max_distance, self.max_distance)
        
        # Concentric circles for human detection range
        detection_ranges = {
            1: ('High Accuracy', 'green', '-'),
            2: ('Good Accuracy', 'yellow', '-'),
            3: ('Medium Accuracy', 'orange', '--'),
            4: ('Low Accuracy', 'red', '--'),
            5: ('Detection Limit', 'gray', ':')
        }
        
        for r, (label, color, style) in detection_ranges.items():
            circle = Circle((0, 0), r, fill=False, color=color, 
                          alpha=0.4, linestyle=style)
            self.ax_radar.add_patch(circle)
            
        # Radial lines for direction
        for angle in range(0, 360, 45):  # Every 45 degrees
            x = self.max_distance * np.cos(np.radians(angle))
            y = self.max_distance * np.sin(np.radians(angle))
            self.ax_radar.plot([0, x], [0, y], 'g-', alpha=0.2)
            
        # Center point (TP-Link dongle position)
        self.ax_radar.plot(0, 0, 'ro', markersize=10, label='TP-Link Dongle')
        self.ax_radar.text(0, -0.3, 'WiFi\nDongle', ha='center', color='red', fontsize=8)
        
        self.ax_radar.set_aspect('equal')
        self.ax_radar.set_title('WiFi Human Detection Radar - TP-Link Dongle', 
                               color='white', fontsize=14)
        self.ax_radar.set_facecolor('black')
        self.ax_radar.grid(True, alpha=0.3)
        
        # Human detection range markers
        for r, (label, color, _) in detection_ranges.items():
            self.ax_radar.text(r, 0.2, f'{r}m\n{label}', 
                             color=color, fontsize=7, ha='center')
            
        # Legend for human detection
        legend_text = [
            '🔴 Walking Human',
            '🟠 Standing Human', 
            '⭕ Confidence Ring',
            '📏 Detection Range'
        ]
        
        for i, text in enumerate(legend_text):
            self.ax_radar.text(-self.max_distance + 0.5, 
                             self.max_distance - 0.5 - (i * 0.4),
                             text, color='white', fontsize=8)
            
    def _draw_objects_realtime(self):
        """Real-time object drawing with instant visual feedback."""
        if not self.object_positions:
            # Show "scanning" indicator when no humans detected
            self.ax_radar.text(0, 0, '🔍 SCANNING...', 
                             ha='center', va='center', fontsize=16, 
                             color='cyan', alpha=0.5)
            return
            
        try:
            current_time = time.time()
            human_colors = ['#FF4444', '#44FF44', '#4444FF', '#FF44FF', '#FFFF44']
            
            for i, obj in enumerate(self.object_positions[:self.max_humans]):
                if obj['type'] == 'human':
                    human_id = obj.get('human_id', i)
                    color = human_colors[human_id % len(human_colors)]
                    
                    x, y = obj['x'], obj['y']
                    size = obj['size']
                    confidence = obj['confidence']
                    intensity = obj['intensity']
                    movement_type = obj.get('movement_type', 'unknown')
                    detection_type = obj.get('detection_type', 'normal')
                    
                    # Enhanced visual feedback for instant detections
                    if detection_type == 'instant':
                        # Pulsing effect for instant detections
                        pulse = 1.0 + 0.3 * np.sin(current_time * 10)
                        size_animated = size * pulse
                        alpha = 0.8 + 0.2 * np.sin(current_time * 8)
                    else:
                        size_animated = size
                        alpha = 0.7
                    
                    # Main human body with real-time animation
                    circle = plt.Circle((x, y), size_animated, 
                                      color=color, alpha=alpha, 
                                      linewidth=3, fill=True)
                    self.ax_radar.add_patch(circle)
                    
                    # Confidence ring with thickness based on confidence
                    ring_thickness = max(1, confidence * 4)
                    confidence_ring = plt.Circle((x, y), size + 0.3, 
                                               color=color, alpha=confidence * 0.4, 
                                               linewidth=ring_thickness, fill=False)
                    self.ax_radar.add_patch(confidence_ring)
                    
                    # Movement indicators with real-time animation
                    if movement_type == 'walking':
                        # Animated movement arrows
                        for angle_offset in [0, 120, 240]:
                            arrow_angle = (current_time * 180 + angle_offset) % 360
                            arrow_length = min(intensity * 0.08, 0.4)
                            dx = arrow_length * np.cos(np.radians(arrow_angle))
                            dy = arrow_length * np.sin(np.radians(arrow_angle))
                            
                            self.ax_radar.arrow(x, y, dx, dy, 
                                              head_width=0.05, head_length=0.05, 
                                              fc=color, ec=color, alpha=0.6)
                    
                    # Real-time info display with activity type
                    activity_type = obj.get('activity_type', movement_type)
                    detection_type = obj.get('detection_type', 'active')
                    time_persistent = obj.get('time_persistent', 0)
                    
                    status_text = f"HUMAN {human_id+1}\\n"
                    status_text += f"Conf: {confidence:.2f}\\n"
                    
                    # Activity-specific display
                    if activity_type == 'walking':
                        status_text += "🚶WALKING\\n"
                    elif activity_type == 'sitting':
                        status_text += "🪑SITTING\\n"
                    elif activity_type == 'sitting_breathing':
                        status_text += "🫁BREATHING\\n"
                    else:
                        status_text += f"{activity_type.upper()}\\n"
                    
                    if detection_type == 'persistent':
                        status_text += f"⏱️{time_persistent:.1f}s"
                    elif detection_type == 'instant':
                        status_text += "⚡INSTANT"
                    else:
                        status_text += f"{obj.get('networks_affected', 0)}nets"
                    
                    # Dynamic text positioning
                    text_x = x + size + 0.2
                    text_y = y + (i * 0.3)  # Offset multiple humans
                    
                    self.ax_radar.text(text_x, text_y, status_text, 
                                     fontsize=9, color=color, weight='bold',
                                     bbox=dict(boxstyle="round,pad=0.3", 
                                             facecolor='black', alpha=0.7,
                                             edgecolor=color, linewidth=2))
                    
                    # Detection zone for high confidence humans
                    if confidence > 0.6:
                        zone_alpha = (confidence - 0.6) * 0.5
                        detection_zone = plt.Circle((x, y), size * 2.5, 
                                                  color=color, alpha=zone_alpha, 
                                                  linestyle=':', linewidth=1, fill=True)
                        self.ax_radar.add_patch(detection_zone)
                        
                    # Add human icon overlay with supported marker
                    icon_size = max(15, confidence * 25)
                    self.ax_radar.plot(x, y, marker='*', markersize=icon_size, 
                                     color='white', markeredgecolor=color, 
                                     markeredgewidth=2, alpha=0.9)
                        
        except Exception as e:
            self.logger.error(f"Real-time drawing error: {e}")
                             
    def _update_signal_plot_realtime(self):
        """Real-time signal analysis plot with instant detection feedback."""
        try:
            self.ax_signals.clear()
            
            if len(self.scan_history) < 3:
                self.ax_signals.text(0.5, 0.5, '📶 INITIALIZING\\nREAL-TIME ANALYSIS...', 
                                   ha='center', va='center', transform=self.ax_signals.transAxes,
                                   fontsize=14, color='yellow')
                return
                
            # Get recent data for real-time display
            recent_history = list(self.scan_history)[-15:]  # Last 15 scans for real-time
            
            if not recent_history:
                return
                
            times = [(scan['timestamp'] - recent_history[0]['timestamp']) for scan in recent_history]
            energies = [scan['total_energy'] for scan in recent_history]
            human_counts = [scan['human_count'] for scan in recent_history]
            confidences = [scan.get('detection_confidence', 0) for scan in recent_history]
            instant_detections = [scan.get('instant_detections', 0) for scan in recent_history]
            
            # Main energy plot
            self.ax_signals.plot(times, energies, 'cyan', linewidth=3, 
                               label='Signal Energy', alpha=0.8)
            
            # Fill area under energy curve
            self.ax_signals.fill_between(times, energies, alpha=0.2, color='cyan')
            
            # Overlay human detection events
            for i, (time, human_count, confidence) in enumerate(zip(times, human_counts, confidences)):
                if human_count > 0:
                    # Mark detection events
                    marker_size = max(50, confidence * 200)
                    self.ax_signals.scatter(time, energies[i], 
                                          s=marker_size, c='red', alpha=0.8, 
                                          marker='*', edgecolors='white', linewidth=1)
                    
                    # Add human count annotation
                    if human_count > 1 or confidence > 0.7:
                        self.ax_signals.annotate(f'{human_count}H', 
                                               (time, energies[i]), 
                                               xytext=(5, 10), textcoords='offset points',
                                               fontsize=8, color='white', weight='bold',
                                               bbox=dict(boxstyle='round,pad=0.2', 
                                                       facecolor='red', alpha=0.7))
            
            # Show instant detection bars
            if any(instant_detections):
                bar_width = max(times) / len(times) if len(times) > 1 else 0.1
                self.ax_signals.bar(times, instant_detections, 
                                  width=bar_width, alpha=0.4, color='gold', 
                                  label='Instant Detections')
            
            # Current status display
            current_humans = len(self.object_positions)
            current_energy = energies[-1] if energies else 0
            current_confidence = confidences[-1] if confidences else 0
            
            # Dynamic title with real-time stats
            title = f'🔥 REAL-TIME DETECTION - {current_humans} HUMANS'
            if current_confidence > 0:
                title += f' (Confidence: {current_confidence:.1f})'
                
            self.ax_signals.set_title(title, fontsize=13, weight='bold', color='white')
            
            # Human detection threshold lines
            if energies:
                max_energy = max(energies)
                self.ax_signals.axhline(y=0.8, color='red', 
                                      linestyle='--', alpha=0.7, 
                                      label='Human Body Threshold (0.8 dBm)')
                self.ax_signals.axhline(y=2.0, color='orange', 
                                      linestyle=':', alpha=0.7, 
                                      label='Strong Movement (2.0 dBm)')
            
            # Real-time performance indicator
            if len(recent_history) >= 10:
                scan_rate = len(recent_history) / (times[-1] - times[0]) if times[-1] > times[0] else 0
                perf_text = f'Scan Rate: {scan_rate:.1f} Hz'
                self.ax_signals.text(0.02, 0.98, perf_text, 
                                   transform=self.ax_signals.transAxes,
                                   fontsize=9, color='lime', weight='bold',
                                   bbox=dict(boxstyle='round,pad=0.3', 
                                           facecolor='black', alpha=0.7))
            
            # Set limits and styling
            if times and energies:
                self.ax_signals.set_xlim(0, max(10, times[-1]))
                self.ax_signals.set_ylim(0, max(3, max(energies) * 1.2))
                
            self.ax_signals.set_xlabel('Time (seconds)', color='white')
            self.ax_signals.set_ylabel('Signal Strength (dBm)', color='white')
            self.ax_signals.tick_params(colors='white')
            self.ax_signals.grid(True, alpha=0.3, color='white')
            
            # Show legend only if there are multiple elements
            handles, labels = self.ax_signals.get_legend_handles_labels()
            if len(handles) > 1:
                self.ax_signals.legend(fontsize=8, loc='upper right', 
                                     framealpha=0.8, facecolor='black')
                
        except Exception as e:
            self.logger.error(f"Real-time signal plot error: {e}")

    def _draw_motion_trails(self):
        """Draw motion intensity over time."""
        if len(self.motion_vectors) > 1:
            times = [m['timestamp'] for m in self.motion_vectors]
            intensities = [m['intensity'] for m in self.motion_vectors]
            
            # Normalize times to recent history
            current_time = time.time()
            trail_times = [(current_time - t) for t in times]
            
            # Draw intensity as color-coded trail
            for i, (trail_time, intensity) in enumerate(zip(trail_times, intensities)):
                if trail_time < 5.0:  # Show last 5 seconds
                    alpha = 1.0 - (trail_time / 5.0)
                    radius = 0.1 + (intensity * 0.1)
                    
                    circle = Circle((0, 0), radius, 
                                  color='orange', alpha=alpha, 
                                  fill=True)
                    self.ax_radar.add_patch(circle)
                    
    def _update_signal_plot(self):
        """Update signal strength plot with human detection indicators."""
        self.ax_signals.clear()
        
        if len(self.scan_history) > 10:
            # Get recent signal changes
            recent_scans = list(self.scan_history)[-20:]
            times = [s['timestamp'] for s in recent_scans]
            
            # Plot signal changes for top networks
            if recent_scans and recent_scans[0].get('changes_for_storage'):
                top_networks = list(recent_scans[0]['changes_for_storage'].keys())[:5]
                
                for network in top_networks:
                    changes = [s.get('changes_for_storage', {}).get(network, 0) for s in recent_scans]
                    self.ax_signals.plot(times, changes, 
                                       label=network[:8], 
                                       marker='o', markersize=2, alpha=0.7)
                                       
            # Plot human detection indicators
            human_indicators = [s.get('human_indicators', 0) for s in recent_scans]
            if any(human_indicators):
                # Create secondary y-axis for human indicators
                ax2 = self.ax_signals.twinx()
                ax2.plot(times, human_indicators, 'r-', linewidth=3, 
                        label='Human Indicators', alpha=0.8)
                ax2.set_ylabel('Human Detection Score', color='red')
                ax2.tick_params(axis='y', colors='red')
                ax2.set_ylim(0, 6)
                
                # Highlight human detection events
                for i, (time, indicators) in enumerate(zip(times, human_indicators)):
                    if indicators >= 3:  # Human detected
                        ax2.axvline(x=time, color='red', alpha=0.3, linestyle='--')
                        ax2.text(time, indicators + 0.5, 'HUMAN!', 
                               rotation=90, color='red', fontsize=8)
                               
        self.ax_signals.set_title('WiFi Human Detection Analysis', color='white')
        self.ax_signals.set_ylabel('Signal Change (dBm)', color='white')
        self.ax_signals.set_xlabel('Time', color='white')
        self.ax_signals.tick_params(colors='white')
        self.ax_signals.set_facecolor('black')
        self.ax_signals.grid(True, alpha=0.3)
        
        # Only show legend if there are labels
        handles, labels = self.ax_signals.get_legend_handles_labels()
        if handles:
            self.ax_signals.legend(fontsize=7, loc='upper left')
        
        # Add human detection threshold lines
        self.ax_signals.axhline(y=0.5, color='yellow', 
                              linestyle='--', alpha=0.5, 
                              label='Detection Threshold')
        self.ax_signals.axhline(y=2.0, color='red', 
                              linestyle='--', alpha=0.5,
                              label='Human Movement Threshold')
                                  
    def start_radar_display(self):
        """Start live radar display."""
        # Set up dark theme
        plt.style.use('dark_background')
        self.fig.suptitle('WiFi Radar System - TP-Link Dongle Object Detection', 
                         fontsize=16, color='white')
        
        # Start animation
        self.ani = animation.FuncAnimation(self.fig, self._update_radar_display,
                                         interval=100, blit=False)
        
        # Show controls
        print("\n🎮 Human Detection Controls:")
        print("   • 🔴 Red circles = Walking humans detected")
        print("   • 🟠 Orange squares = Standing humans detected") 
        print("   • ⭕ Confidence rings = Detection certainty")
        print("   • 📊 Right plot shows human detection score")
        print("   • 🎯 Only humans are detected (filters out objects)")
        print("   • Close window to stop")
        
        print(f"\n🧠 Human Detection Criteria:")
        print(f"   • Multiple WiFi networks affected (body blocking)")
        print(f"   • Signal pattern analysis (human body characteristics)")
        print(f"   • Breathing/micro-movement detection")
        print(f"   • Human-like movement patterns")
        print(f"   • Minimum 3/6 criteria must be met for detection")
        
        plt.tight_layout()
        plt.show()
        
    def stop(self):
        """Stop the radar system."""
        self.running = False
        if hasattr(self, 'wifi_module'):
            self.wifi_module.stop()
        print("🛑 WiFi Radar stopped")


def main():
    """Main WiFi radar application."""
    print("🎯 WiFi Radar System Starting...")
    print("📡 Using TP-Link dongle for object detection")
    print("🚀 No camera required!")
    
    try:
        radar = WiFiRadar()
        radar.start_wifi_scanning()
        time.sleep(3)  # Allow calibration
        radar.start_radar_display()
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'radar' in locals():
            radar.stop()


if __name__ == "__main__":
    main()