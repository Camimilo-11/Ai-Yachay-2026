"""
Camera-based person detection module for WiFi sensing human presence system.

This module provides person detection using OpenCV and deep learning models.
It can detect when a person is visible in the camera frame and track their position.
"""

import cv2
import numpy as np
import time
from typing import Tuple, List, Optional, Dict, Any
import threading
import queue
from dataclasses import dataclass
from loguru import logger


@dataclass
class PersonDetection:
    """Data class for person detection results."""
    bbox: Tuple[int, int, int, int]  # (x, y, width, height)
    confidence: float
    center: Tuple[int, int]
    timestamp: float


@dataclass
class CameraFrame:
    """Data class for camera frame with metadata."""
    frame: np.ndarray
    timestamp: float
    frame_id: int


class PersonDetector:
    """Person detection using OpenCV's DNN or HOG detector."""
    
    def __init__(self, detection_method: str = "hog", confidence_threshold: float = 0.5):
        """
        Initialize the person detector.
        
        Args:
            detection_method: "hog" for HOG+SVM or "dnn" for deep learning
            confidence_threshold: Minimum confidence for detections
        """
        self.detection_method = detection_method
        self.confidence_threshold = confidence_threshold
        
        if detection_method == "hog":
            self.hog = cv2.HOGDescriptor()
            self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        elif detection_method == "dnn":
            # You can replace this with YOLO, MobileNet, etc.
            self._load_dnn_model()
        else:
            raise ValueError(f"Unsupported detection method: {detection_method}")
            
        logger.info(f"Initialized person detector with method: {detection_method}")
    
    def _load_dnn_model(self):
        """Load DNN model for person detection."""
        # Example using OpenCV's DNN with a pre-trained model
        # You would need to download appropriate model files
        try:
            self.net = cv2.dnn.readNetFromDarknet(
                "models/yolo-person.cfg", 
                "models/yolo-person.weights"
            )
            self.output_layers = self.net.getUnconnectedOutLayersNames()
            logger.info("DNN model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load DNN model: {e}. Falling back to HOG.")
            self.detection_method = "hog"
            self.hog = cv2.HOGDescriptor()
            self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    
    def detect_persons(self, frame: np.ndarray) -> List[PersonDetection]:
        """
        Detect persons in the given frame.
        
        Args:
            frame: Input image frame
            
        Returns:
            List of PersonDetection objects
        """
        if self.detection_method == "hog":
            return self._detect_hog(frame)
        elif self.detection_method == "dnn":
            return self._detect_dnn(frame)
        else:
            return []
    
    def _detect_hog(self, frame: np.ndarray) -> List[PersonDetection]:
        """Detect persons using HOG+SVM."""
        # Convert to grayscale if needed
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
            
        # Detect people
        boxes, weights = self.hog.detectMultiScale(
            gray,
            winStride=(8, 8),
            padding=(32, 32),
            scale=1.05
        )
        
        detections = []
        for (x, y, w, h), weight in zip(boxes, weights):
            if weight > self.confidence_threshold:
                center_x = x + w // 2
                center_y = y + h // 2
                detection = PersonDetection(
                    bbox=(x, y, w, h),
                    confidence=float(weight),
                    center=(center_x, center_y),
                    timestamp=time.time()
                )
                detections.append(detection)
        
        return detections
    
    def _detect_dnn(self, frame: np.ndarray) -> List[PersonDetection]:
        """Detect persons using DNN model."""
        height, width = frame.shape[:2]
        
        # Create blob from image
        blob = cv2.dnn.blobFromImage(
            frame, 1/255.0, (416, 416), swapRB=True, crop=False
        )
        
        self.net.setInput(blob)
        outputs = self.net.forward(self.output_layers)
        
        # Parse detections
        boxes = []
        confidences = []
        for output in outputs:
            for detection in output:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                
                # Filter for person class (usually class 0 in COCO)
                if class_id == 0 and confidence > self.confidence_threshold:
                    # Scale bounding box back to original image size
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)
                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)
                    
                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))
        
        # Apply NMS
        indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
        
        detections = []
        if len(indices) > 0:
            for i in indices.flatten():
                x, y, w, h = boxes[i]
                center_x = x + w // 2
                center_y = y + h // 2
                detection = PersonDetection(
                    bbox=(x, y, w, h),
                    confidence=confidences[i],
                    center=(center_x, center_y),
                    timestamp=time.time()
                )
                detections.append(detection)
        
        return detections


class CameraModule:
    """Main camera module for person detection and tracking."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize camera module.
        
        Args:
            config: Camera configuration dictionary
        """
        self.config = config
        self.device_id = config.get("device_id", 0)
        self.width = config.get("width", 640)
        self.height = config.get("height", 480)
        self.fps = config.get("fps", 30)
        
        # Initialize person detector
        detection_config = config.get("person_detection", {})
        confidence_threshold = detection_config.get("confidence_threshold", 0.5)
        
        self.person_detector = PersonDetector(
            detection_method="hog",  # Default to HOG for reliability
            confidence_threshold=confidence_threshold
        )
        
        # Camera capture
        self.cap = None
        self.is_running = False
        self.frame_queue = queue.Queue(maxsize=10)
        self.detection_queue = queue.Queue(maxsize=50)
        
        # Threading
        self.capture_thread = None
        self.detection_thread = None
        
        # Statistics
        self.frame_count = 0
        self.last_person_seen_time = 0
        self.person_visible = False
        
        logger.info(f"Camera module initialized: {self.width}x{self.height}@{self.fps}fps")
    
    def start(self) -> bool:
        """Start the camera capture and detection."""
        try:
            self.cap = cv2.VideoCapture(self.device_id)
            if not self.cap.isOpened():
                logger.error(f"Could not open camera device {self.device_id}")
                return False
            
            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            self.is_running = True
            
            # Start threads
            self.capture_thread = threading.Thread(target=self._capture_loop)
            self.detection_thread = threading.Thread(target=self._detection_loop)
            
            self.capture_thread.daemon = True
            self.detection_thread.daemon = True
            
            self.capture_thread.start()
            self.detection_thread.start()
            
            logger.info("Camera module started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start camera module: {e}")
            return False
    
    def stop(self):
        """Stop the camera capture and detection."""
        self.is_running = False
        
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)
        
        if self.detection_thread and self.detection_thread.is_alive():
            self.detection_thread.join(timeout=2)
        
        if self.cap:
            self.cap.release()
        
        logger.info("Camera module stopped")
    
    def _capture_loop(self):
        """Main capture loop running in separate thread."""
        while self.is_running:
            try:
                ret, frame = self.cap.read()
                if ret:
                    camera_frame = CameraFrame(
                        frame=frame,
                        timestamp=time.time(),
                        frame_id=self.frame_count
                    )
                    
                    # Add to queue (drop old frames if queue is full)
                    if not self.frame_queue.full():
                        self.frame_queue.put(camera_frame)
                    else:
                        try:
                            self.frame_queue.get_nowait()
                            self.frame_queue.put(camera_frame)
                        except queue.Empty:
                            pass
                    
                    self.frame_count += 1
                else:
                    logger.warning("Failed to capture frame")
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error in capture loop: {e}")
                time.sleep(0.1)
    
    def _detection_loop(self):
        """Main detection loop running in separate thread."""
        while self.is_running:
            try:
                # Get frame from queue
                camera_frame = self.frame_queue.get(timeout=1)
                
                # Detect persons
                detections = self.person_detector.detect_persons(camera_frame.frame)
                
                # Update person visibility status
                if detections:
                    self.person_visible = True
                    self.last_person_seen_time = camera_frame.timestamp
                else:
                    # Consider person gone if not seen for 2 seconds
                    if (camera_frame.timestamp - self.last_person_seen_time) > 2.0:
                        self.person_visible = False
                
                # Store detection results
                detection_result = {
                    "frame_id": camera_frame.frame_id,
                    "timestamp": camera_frame.timestamp,
                    "detections": detections,
                    "person_visible": self.person_visible,
                    "frame": camera_frame.frame  # Keep frame for visualization
                }
                
                # Always add detection result, discard old ones if queue is full
                try:
                    self.detection_queue.put_nowait(detection_result)
                except queue.Full:
                    # Remove oldest item and add new one
                    try:
                        self.detection_queue.get_nowait()
                        self.detection_queue.put_nowait(detection_result)
                    except queue.Empty:
                        self.detection_queue.put_nowait(detection_result)
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in detection loop: {e}")
    
    def get_latest_detection(self) -> Optional[Dict[str, Any]]:
        """Get the latest detection result."""
        latest = None
        
        # Drain the queue and get the most recent detection
        try:
            while True:
                latest = self.detection_queue.get_nowait()
        except queue.Empty:
            pass
            
        return latest
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current camera module status."""
        return {
            "is_running": self.is_running,
            "person_visible": self.person_visible,
            "last_person_seen_time": self.last_person_seen_time,
            "frame_count": self.frame_count,
            "time_since_last_person": time.time() - self.last_person_seen_time if self.last_person_seen_time > 0 else float('inf')
        }
    
    def visualize_detections(self, detection_result: Dict[str, Any]) -> np.ndarray:
        """
        Draw detection results on frame for visualization.
        
        Args:
            detection_result: Detection result from get_latest_detection()
            
        Returns:
            Frame with drawn bounding boxes and status
        """
        frame = detection_result["frame"].copy()
        detections = detection_result["detections"]
        
        # Draw bounding boxes
        for detection in detections:
            x, y, w, h = detection.bbox
            confidence = detection.confidence
            
            # Draw rectangle
            color = (0, 255, 0) if detection_result["person_visible"] else (0, 0, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            
            # Draw confidence
            label = f"Person: {confidence:.2f}"
            cv2.putText(frame, label, (x, y - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Draw status
        status_text = f"Person Visible: {detection_result['person_visible']}"
        cv2.putText(frame, status_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        timestamp_text = f"Frame: {detection_result['frame_id']}"
        cv2.putText(frame, timestamp_text, (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return frame


def main():
    """Test the camera module."""
    config = {
        "device_id": 0,
        "width": 640,
        "height": 480,
        "fps": 30,
        "person_detection": {
            "confidence_threshold": 0.5
        }
    }
    
    camera = CameraModule(config)
    
    if camera.start():
        print("Camera started. Press 'q' to quit.")
        
        try:
            while True:
                detection_result = camera.get_latest_detection()
                
                if detection_result:
                    frame_with_detections = camera.visualize_detections(detection_result)
                    cv2.imshow("Person Detection", frame_with_detections)
                    
                    # Print status
                    status = camera.get_current_status()
                    if status["person_visible"]:
                        print(f"Person visible - Frame {detection_result['frame_id']}")
                    else:
                        print(f"No person - Time since last: {status['time_since_last_person']:.1f}s")
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            camera.stop()
            cv2.destroyAllWindows()
    else:
        print("Failed to start camera")


if __name__ == "__main__":
    main()