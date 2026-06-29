"""
camera.py - OpenCV camera feed handler (Singleton)
Annotates frames with student names by looking up their student_ids in the DB.
"""

import cv2
import numpy as np
import threading
import time
from typing import Optional, Generator
from datetime import datetime


class Camera:
    """Singleton camera class for managing webcam feed."""

    _instance: Optional["Camera"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_running = False
        self._current_frame: Optional[np.ndarray] = None
        self._raw_frame: Optional[np.ndarray] = None  # Unannotated frame for snapshots
        self._frame_lock = threading.Lock()
        self._capture_thread: Optional[threading.Thread] = None
        self._recognition_results = []
        self._results_lock = threading.Lock()
        self._recognition_callback = None
        self._last_recognition_time = 0
        self._recognition_interval = 0.3  # Run recognition every 300ms
        self._frame_count = 0
        self._fps = 0
        self._last_fps_time = time.time()

    def set_recognition_callback(self, callback):
        """Set callback function called with recognized student_ids."""
        self._recognition_callback = callback

    def start(self) -> dict:
        """Start the camera capture."""
        if self._is_running:
            return {"success": True, "message": "Camera already running"}

        # Try multiple camera indices
        cap = None
        for idx in [0, 1, 2]:
            try:
                test_cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if test_cap.isOpened():
                    ret, frame = test_cap.read()
                    if ret and frame is not None:
                        cap = test_cap
                        print(f"[Camera] Opened camera at index {idx}")
                        break
                    test_cap.release()
            except Exception:
                pass

        if cap is None:
            try:
                test_cap = cv2.VideoCapture(0)
                if test_cap.isOpened():
                    ret, frame = test_cap.read()
                    if ret and frame is not None:
                        cap = test_cap
            except Exception:
                pass

        if cap is None:
            return {
                "success": False,
                "message": "Could not access camera. Please check if your webcam is connected and not in use by another application."
            }

        # Configure camera
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._cap = cap
        self._is_running = True
        self._frame_count = 0
        self._last_fps_time = time.time()

        # Start capture thread
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True
        )
        self._capture_thread.start()

        return {"success": True, "message": "Camera started successfully"}

    def stop(self):
        """Stop the camera capture."""
        self._is_running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)

        if self._cap:
            self._cap.release()
            self._cap = None

        with self._frame_lock:
            self._current_frame = None
            self._raw_frame = None

        with self._results_lock:
            self._recognition_results = []

        print("[Camera] Camera stopped.")

    def _capture_loop(self):
        """Background thread that continuously captures frames."""
        while self._is_running and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                print("[Camera] Frame capture failed, retrying...")
                time.sleep(0.05)
                continue

            # Calculate FPS
            self._frame_count += 1
            now = time.time()
            if now - self._last_fps_time >= 1.0:
                self._fps = self._frame_count
                self._frame_count = 0
                self._last_fps_time = now

            # Save the raw unannotated frame for snapshot capture
            with self._frame_lock:
                self._raw_frame = frame.copy()

            # Run recognition at intervals
            if (now - self._last_recognition_time) >= self._recognition_interval:
                self._last_recognition_time = now
                self._run_recognition(frame)

            # Annotate frame with current results
            annotated = self._annotate_frame(frame.copy())

            with self._frame_lock:
                self._current_frame = annotated

            time.sleep(0.01)

    def _run_recognition(self, frame: np.ndarray):
        """Run face recognition on the given frame."""
        try:
            from face_engine import recognize_face
            results = recognize_face(frame)

            with self._results_lock:
                self._recognition_results = results

            # Trigger callback for attendance marking
            if self._recognition_callback and results:
                for student_id, top, right, bottom, left in results:
                    if student_id != "Unknown":
                        self._recognition_callback(student_id)

        except Exception as e:
            print(f"[Camera] Recognition error: {e}")

    def _annotate_frame(self, frame: np.ndarray) -> np.ndarray:
        """Draw bounding boxes and labels on frame."""
        with self._results_lock:
            results = list(self._recognition_results)

        # Import DB inside method to avoid circular dependency
        from database import get_student_by_id

        # Color scheme
        COLOR_KNOWN = (0, 212, 170)    # Teal - recognized
        COLOR_UNKNOWN = (76, 76, 255)   # Red (BGR) - unknown

        for student_id, top, right, bottom, left in results:
            name = "Unknown"
            if student_id != "Unknown":
                # Look up student's actual name
                student = get_student_by_id(student_id)
                if student:
                    name = student["name"]
                else:
                    name = student_id.upper()

            color = COLOR_KNOWN if student_id != "Unknown" else COLOR_UNKNOWN

            # Draw bounding box
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

            # Draw label background
            label = name
            label_size, baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1
            )
            label_y = top - 10 if top - 10 > 10 else top + label_size[1] + 10

            cv2.rectangle(
                frame,
                (left, label_y - label_size[1] - 8),
                (left + label_size[0] + 8, label_y + baseline),
                color,
                cv2.FILLED
            )

            # Draw label text
            cv2.putText(
                frame,
                label,
                (left + 4, label_y - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 0),
                1,
                cv2.LINE_AA
            )

        # Draw FPS indicator
        fps_text = f"FPS: {self._fps}"
        cv2.putText(
            frame, fps_text, (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 212, 170), 1, cv2.LINE_AA
        )

        # Draw timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            frame, timestamp, (10, frame.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (139, 148, 158), 1, cv2.LINE_AA
        )

        return frame

    def generate_frames(self) -> Generator[bytes, None, None]:
        """
        MJPEG frame generator.
        """
        while self._is_running:
            with self._frame_lock:
                frame = self._current_frame.copy() if self._current_frame is not None else None

            if frame is None:
                frame = self._get_placeholder_frame()

            try:
                ret, buffer = cv2.imencode(
                    ".jpg", frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                if not ret:
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" +
                    buffer.tobytes() +
                    b"\r\n"
                )
            except Exception as e:
                print(f"[Camera] Frame encoding error: {e}")

            time.sleep(0.033)  # ~30fps max

    def get_raw_frame_jpeg(self) -> Optional[bytes]:
        """Capture the current raw unannotated frame from the webcam as JPEG bytes."""
        with self._frame_lock:
            frame = self._raw_frame.copy() if self._raw_frame is not None else None

        if frame is None:
            return None

        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if ret:
            return buffer.tobytes()
        return None

    @staticmethod
    def _get_placeholder_frame() -> np.ndarray:
        """Generate a placeholder frame when camera is not ready."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (22, 27, 34)  # Dark background

        text = "Camera initializing..."
        size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        x = (640 - size[0]) // 2
        y = (480 + size[1]) // 2
        cv2.putText(
            frame, text, (x, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 212, 170), 2, cv2.LINE_AA
        )
        return frame

    @property
    def is_running(self) -> bool:
        return self._is_running

    @staticmethod
    def get_no_camera_frame() -> bytes:
        """Return a static 'Camera Offline' JPEG frame."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (22, 27, 34)

        lines = [
            ("CAMERA OFFLINE", 0.9, (76, 76, 255), 2, -30),
            ("Click 'Start Camera' to begin", 0.55, (139, 148, 158), 1, 30),
        ]

        for text, scale, color, thickness, y_offset in lines:
            size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)[0]
            x = (640 - size[0]) // 2
            y = 240 + y_offset
            cv2.putText(
                frame, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA
            )

        # Draw camera icon
        cv2.circle(frame, (320, 160), 50, (50, 50, 60), -1)
        cv2.circle(frame, (320, 160), 35, (30, 30, 40), -1)
        cv2.circle(frame, (320, 160), 20, (76, 76, 255), 2)
        cv2.circle(frame, (320, 160), 8, (76, 76, 255), -1)

        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buffer.tobytes()


# Module-level singleton instance
camera = Camera()
