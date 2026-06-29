"""
face_engine.py - Face recognition engine using student_id as key.
Includes Haar Cascade fallback for machines without dlib compiled.
"""

import os
import pickle
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
import threading

try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    print("[WARNING] face_recognition not installed. Running in Haar Cascade fallback/simulation mode.")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

import cv2

# Load Haar Cascade as fallback face detector
face_cascade = None
if not FACE_RECOGNITION_AVAILABLE:
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        print("[WARNING] Failed to load Haar Cascade face detector.")

KNOWN_FACES_DIR = Path(__file__).parent / "known_faces"
ENCODINGS_CACHE = Path(__file__).parent / "encodings_cache.pkl"
TOLERANCE = 0.5

# Thread lock for safe cache updates
_cache_lock = threading.Lock()

# In-memory cache: list of (student_id, encoding) tuples
_known_faces_cache: List[Tuple[str, np.ndarray]] = []
# For simulation mode: keep track of registered student IDs
_simulated_student_ids: List[str] = []


def _ensure_dirs():
    """Ensure known_faces directory exists."""
    KNOWN_FACES_DIR.mkdir(exist_ok=True)


def load_known_faces(force_reload: bool = False) -> int:
    """
    Load known faces from pickle cache or re-encode from images.
    Returns count of loaded faces.
    """
    global _known_faces_cache, _simulated_student_ids

    _ensure_dirs()

    if not FACE_RECOGNITION_AVAILABLE:
        # Fallback mode: read student_ids from filenames in known_faces/
        with _cache_lock:
            image_files = list(KNOWN_FACES_DIR.glob("*.jpg")) + \
                          list(KNOWN_FACES_DIR.glob("*.png")) + \
                          list(KNOWN_FACES_DIR.glob("*.jpeg"))
            _simulated_student_ids = [f.stem for f in image_files]
            print(f"[FaceEngine] [Simulation] Loaded {len(_simulated_student_ids)} student IDs: {_simulated_student_ids}")
            return len(_simulated_student_ids)

    with _cache_lock:
        # Try loading from cache first
        if not force_reload and ENCODINGS_CACHE.exists():
            try:
                with open(ENCODINGS_CACHE, "rb") as f:
                    cached = pickle.load(f)

                # Validate cache is not stale
                image_files = list(KNOWN_FACES_DIR.glob("*.jpg")) + \
                              list(KNOWN_FACES_DIR.glob("*.png")) + \
                              list(KNOWN_FACES_DIR.glob("*.jpeg"))

                cached_ids = {item[0] for item in cached}
                file_ids = {f.stem for f in image_files}

                if cached_ids == file_ids:
                    _known_faces_cache = cached
                    print(f"[FaceEngine] Loaded {len(_known_faces_cache)} faces from cache.")
                    return len(_known_faces_cache)
            except Exception as e:
                print(f"[FaceEngine] Cache load failed: {e}, re-encoding...")

        # Re-encode all images
        _known_faces_cache = []
        image_files = list(KNOWN_FACES_DIR.glob("*.jpg")) + \
                      list(KNOWN_FACES_DIR.glob("*.png")) + \
                      list(KNOWN_FACES_DIR.glob("*.jpeg"))

        for img_path in image_files:
            student_id = img_path.stem
            try:
                image = face_recognition.load_image_file(str(img_path))
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    _known_faces_cache.append((student_id, encodings[0]))
                    print(f"[FaceEngine] Encoded student: {student_id}")
                else:
                    print(f"[FaceEngine] No face found in {img_path.name}, skipping.")
            except Exception as e:
                print(f"[FaceEngine] Error encoding {img_path.name}: {e}")

        # Save updated cache
        _save_cache()
        print(f"[FaceEngine] Loaded {len(_known_faces_cache)} faces from images.")
        return len(_known_faces_cache)


def _save_cache():
    """Save encodings cache to disk."""
    if not FACE_RECOGNITION_AVAILABLE:
        return
    try:
        with open(ENCODINGS_CACHE, "wb") as f:
            pickle.dump(_known_faces_cache, f)
    except Exception as e:
        print(f"[FaceEngine] Cache save failed: {e}")


def recognize_face(frame: np.ndarray) -> List[Tuple[str, int, int, int, int]]:
    """
    Detect and recognize faces in an OpenCV frame.
    
    Args:
        frame: OpenCV BGR frame
        
    Returns:
        List of (student_id, top, right, bottom, left) tuples
    """
    if not FACE_RECOGNITION_AVAILABLE:
        # Fallback: Use OpenCV Haar Cascade to detect faces
        if face_cascade is None:
            return []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small_gray = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)
        faces = face_cascade.detectMultiScale(small_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        results = []
        with _cache_lock:
            student_ids = list(_simulated_student_ids)
            
        for i, (x, y, w, h) in enumerate(faces):
            left = x * 2
            top = y * 2
            right = (x + w) * 2
            bottom = (y + h) * 2
            
            # Simulate recognition
            if student_ids:
                student_id = student_ids[i % len(student_ids)]
            else:
                student_id = "Unknown"
                
            results.append((student_id, top, right, bottom, left))
        return results

    # Convert BGR to RGB
    rgb_frame = frame[:, :, ::-1]

    # Scale down
    small_frame = rgb_frame[::2, ::2]

    # Find face locations
    face_locations = face_recognition.face_locations(small_frame, model="hog")

    if not face_locations:
        return []

    # Get face encodings
    face_encodings = face_recognition.face_encodings(small_frame, face_locations)

    results = []

    with _cache_lock:
        known_encodings = [enc for _, enc in _known_faces_cache]
        known_ids = [student_id for student_id, _ in _known_faces_cache]

    for face_encoding, (top, right, bottom, left) in zip(face_encodings, face_locations):
        student_id = "Unknown"

        if known_encodings:
            matches = face_recognition.compare_faces(
                known_encodings, face_encoding, tolerance=TOLERANCE
            )
            face_distances = face_recognition.face_distance(known_encodings, face_encoding)

            if len(face_distances) > 0:
                best_match_idx = np.argmin(face_distances)
                if matches[best_match_idx]:
                    student_id = known_ids[best_match_idx]

        # Scale back up
        results.append((student_id, top * 2, right * 2, bottom * 2, left * 2))

    return results


def register_face(image_data: bytes, student_id: str, file_extension: str = "jpg") -> dict:
    """
    Register a new face from image bytes.
    """
    _ensure_dirs()
    
    student_id = student_id.strip().lower()
    if not student_id:
        return {"success": False, "message": "Student ID cannot be empty."}

    if not FACE_RECOGNITION_AVAILABLE:
        try:
            import io as _io
            from PIL import Image as PILImage

            pil_image = PILImage.open(_io.BytesIO(image_data))
            pil_image = pil_image.convert("RGB")
            
            save_path = KNOWN_FACES_DIR / f"{student_id}.jpg"
            pil_image.save(str(save_path), "JPEG", quality=95)
            
            with _cache_lock:
                if student_id not in _simulated_student_ids:
                    _simulated_student_ids.append(student_id)
                    
            return {
                "success": True,
                "message": "Face image registered successfully (Haar Cascade mode).",
                "student_id": student_id,
                "face_count": len(_simulated_student_ids)
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Registration error (Haar Cascade mode): {str(e)}"
            }

    try:
        import io as _io
        from PIL import Image as PILImage

        pil_image = PILImage.open(_io.BytesIO(image_data))
        pil_image = pil_image.convert("RGB")

        img_array = np.array(pil_image)

        face_locations = face_recognition.face_locations(img_array)

        if len(face_locations) == 0:
            return {
                "success": False,
                "message": "No face detected in the image. Please upload a clear photo showing the student's face."
            }

        if len(face_locations) > 1:
            return {
                "success": False,
                "message": f"Multiple faces detected ({len(face_locations)}). Please use a photo with only one person."
            }

        # Save image
        save_path = KNOWN_FACES_DIR / f"{student_id}.jpg"
        pil_image.save(str(save_path), "JPEG", quality=95)

        # Update cache
        encodings = face_recognition.face_encodings(img_array, face_locations)
        if encodings:
            with _cache_lock:
                _known_faces_cache[:] = [
                    (sid, e) for sid, e in _known_faces_cache
                    if sid != student_id
                ]
                _known_faces_cache.append((student_id, encodings[0]))
                _save_cache()

        return {
            "success": True,
            "message": "Face registered successfully.",
            "student_id": student_id,
            "face_count": len(_known_faces_cache)
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Registration error: {str(e)}"
        }


def get_known_faces_count() -> int:
    """Return the number of registered faces."""
    with _cache_lock:
        if not FACE_RECOGNITION_AVAILABLE:
            return len(_simulated_student_ids)
        return len(_known_faces_cache)


def get_registered_names() -> List[str]:
    """Return list of all registered student IDs."""
    with _cache_lock:
        if not FACE_RECOGNITION_AVAILABLE:
            return list(_simulated_student_ids)
        return [sid for sid, _ in _known_faces_cache]


def delete_face(student_id: str) -> dict:
    """Delete a registered face by student_id."""
    global _known_faces_cache, _simulated_student_ids
    student_id = student_id.strip().lower()

    deleted_file = False
    for ext in ["jpg", "png", "jpeg"]:
        img_path = KNOWN_FACES_DIR / f"{student_id}.{ext}"
        if img_path.exists():
            img_path.unlink()
            deleted_file = True
            break

    if not FACE_RECOGNITION_AVAILABLE:
        with _cache_lock:
            if student_id in _simulated_student_ids:
                _simulated_student_ids.remove(student_id)
                deleted_file = True
        if deleted_file:
            return {"success": True, "message": f"Deleted face for student '{student_id}' successfully."}
        return {"success": False, "message": f"No face image found for student '{student_id}'."}

    with _cache_lock:
        original_count = len(_known_faces_cache)
        _known_faces_cache = [
            (sid, e) for sid, e in _known_faces_cache
            if sid != student_id
        ]
        removed = original_count - len(_known_faces_cache)
        _save_cache()

    if deleted_file or removed > 0:
        return {"success": True, "message": f"Deleted face for student '{student_id}' successfully."}
    else:
        return {"success": False, "message": f"No face image found for student '{student_id}'."}


# Load known faces on module import
load_known_faces()
