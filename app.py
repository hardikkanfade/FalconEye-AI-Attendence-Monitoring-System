"""
app.py - Main Flask application for Multiple User Face Attendance System.
Routes, database operations, and real-time polling.
"""

import os
import io
import time
import base64
import threading
from datetime import datetime
from pathlib import Path
from flask import (
    Flask, render_template, request, jsonify,
    Response, send_file, abort
)
from flask_cors import CORS

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "face-attendance-secret-2024")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload

CORS(app)

# Import modules after app creation
from database import (
    init_db, add_student, get_students, get_student_by_id, delete_student,
    start_class_session, end_class_session, get_active_session, get_class_history,
    mark_student_attendance, get_attendance_records, get_session_stats, export_session_to_csv
)
from camera import camera
from face_engine import (
    load_known_faces, register_face,
    get_known_faces_count, get_registered_names, delete_face
)

# Ensure DB is initialized
init_db()

# Anti-spam: track last attendance mark time per student_id
_last_mark_times = {}
_mark_times_lock = threading.Lock()
ANTI_SPAM_SECONDS = 60

# Track recent notifications for polling
_recent_notifications = []
_notifications_lock = threading.Lock()


def attendance_callback(student_id: str):
    """
    Called by camera when a student is recognized.
    Marks attendance if there is an active class session.
    """
    active_class = get_active_session()
    if not active_class:
        return  # No active session, do not mark attendance

    now = time.time()

    with _mark_times_lock:
        last_time = _last_mark_times.get(student_id, 0)
        if now - last_time < ANTI_SPAM_SECONDS:
            return  # Skip if marked recently
        _last_mark_times[student_id] = now

    # Mark attendance in DB
    class_id = active_class["id"]
    result = mark_student_attendance(class_id, student_id)

    if result["success"]:
        notification = {
            "type": "attendance_marked",
            "student_id": student_id,
            "name": result["name"],
            "time": result["time"],
            "class_name": active_class["class_name"],
            "timestamp": now,
            "message": f"✅ Attendance marked for {result['name']}"
        }
        with _notifications_lock:
            _recent_notifications.append(notification)
            if len(_recent_notifications) > 50:
                _recent_notifications.pop(0)

        print(f"[App] {notification['message']} in class '{active_class['class_name']}'")


# Set recognition callback
camera.set_recognition_callback(attendance_callback)

# ─────────────────────────── API ROUTES ───────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    if not camera.is_running:
        frame_bytes = camera.get_no_camera_frame()
        return Response(
            (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                frame_bytes +
                b"\r\n"
            ),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )
    return Response(
        camera.generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/start_camera", methods=["POST"])
def start_camera():
    result = camera.start()
    return jsonify(result)


@app.route("/stop_camera", methods=["POST"])
def stop_camera():
    camera.stop()
    return jsonify({"success": True, "message": "Camera stopped"})


@app.route("/camera_status")
def camera_status():
    return jsonify({"running": camera.is_running})


# ─────────────────────────── CLASS SESSION ROUTES ───────────────────────────

@app.route("/active_session")
def active_session():
    session = get_active_session()
    return jsonify({"active": session is not None, "session": session})


@app.route("/start_session", methods=["POST"])
def start_session():
    data = request.get_json() or {}
    class_name = data.get("class_name", "").strip()
    subject = data.get("subject", "").strip()
    
    if not class_name or not subject:
        return jsonify({"success": False, "message": "Class Name and Subject are required."}), 400
        
    result = start_class_session(class_name, subject)
    if result["success"]:
        # Auto-start camera
        if not camera.is_running:
            camera.start()
    return jsonify(result)


@app.route("/end_session", methods=["POST"])
def end_session():
    data = request.get_json() or {}
    class_id = data.get("class_id")
    
    if not class_id:
        return jsonify({"success": False, "message": "Class ID is required."}), 400
        
    result = end_class_session(int(class_id))
    # Auto-stop camera
    camera.stop()
    return jsonify(result)


@app.route("/class_history")
def class_history():
    history = get_class_history()
    return jsonify({"history": history, "count": len(history)})


# ─────────────────────────── STUDENT REGISTRATION ───────────────────────────

@app.route("/capture_snapshot")
def capture_snapshot():
    """
    Grabs the current raw frame from the running backend camera.
    Returns it as a base64 encoded string so the UI can show a preview.
    """
    if not camera.is_running:
        return jsonify({"success": False, "message": "Camera must be running to take a snapshot."}), 400
        
    jpeg_bytes = camera.get_raw_frame_jpeg()
    if not jpeg_bytes:
        return jsonify({"success": False, "message": "Could not capture frame. Try again."}), 500
        
    b64_data = base64.b64encode(jpeg_bytes).decode("utf-8")
    return jsonify({
        "success": True,
        "image": f"data:image/jpeg;base64,{b64_data}"
    })


@app.route("/register_student", methods=["POST"])
def register_student_route():
    """Register student details and face image."""
    student_id = request.form.get("student_id", "").strip().lower()
    name = request.form.get("name", "").strip()
    use_snapshot = request.form.get("use_snapshot") == "true"
    
    if not student_id or not name:
        return jsonify({"success": False, "message": "Student ID and Name are required."}), 400
        
    # Get image data
    image_bytes = None
    if use_snapshot:
        if not camera.is_running:
            return jsonify({"success": False, "message": "Camera is not running to capture snapshot."}), 400
        image_bytes = camera.get_raw_frame_jpeg()
        if not image_bytes:
            return jsonify({"success": False, "message": "Failed to capture snapshot from camera stream."}), 500
    else:
        if "photo" not in request.files:
            return jsonify({"success": False, "message": "No photo provided."}), 400
        photo = request.files["photo"]
        if photo.filename == "":
            return jsonify({"success": False, "message": "No photo selected."}), 400
        image_bytes = photo.read()

    # 1. Register student in the database
    db_result = add_student(student_id, name)
    if not db_result["success"]:
        return jsonify(db_result), 400
        
    # 2. Register student face in the face engine
    face_result = register_face(image_bytes, student_id)
    if not face_result["success"]:
        # Rollback database registration if face encoding fails
        delete_student(student_id)
        return jsonify(face_result), 400
        
    # Reload known faces to update cache
    load_known_faces(force_reload=True)
    
    return jsonify({
        "success": True,
        "message": f"Successfully registered student {name} ({student_id.upper()})."
    })


@app.route("/students")
def list_students():
    search = request.args.get("search", "")
    students = get_students(search)
    return jsonify({"students": students, "count": len(students)})


@app.route("/delete_student", methods=["DELETE"])
def delete_student_route():
    data = request.get_json() or {}
    student_id = data.get("student_id", "").strip().lower()
    
    if not student_id:
        return jsonify({"success": False, "message": "Student ID is required."}), 400
        
    # Delete face image
    delete_face(student_id)
    # Delete student from DB
    success = delete_student(student_id)
    
    if success:
        load_known_faces(force_reload=True)
        return jsonify({"success": True, "message": f"Deleted student '{student_id.upper()}' successfully."})
    else:
        return jsonify({"success": False, "message": "Failed to delete student from database."})


# ─────────────────────────── ATTENDANCE LOGS & STATS ───────────────────────────

@app.route("/attendance")
def get_attendance():
    class_id = request.args.get("class_id")
    date_filter = request.args.get("date")
    name_filter = request.args.get("name")
    
    c_id = int(class_id) if class_id else None
    
    records = get_attendance_records(
        class_id=c_id,
        date_filter=date_filter if date_filter else None,
        name_filter=name_filter if name_filter else None
    )
    return jsonify({"records": records, "count": len(records)})


@app.route("/stats")
def get_stats():
    """Get statistics. Supports active class stats or overall stats."""
    class_id_str = request.args.get("class_id")
    total_students = len(get_students())
    
    if class_id_str:
        stats = get_session_stats(int(class_id_str), total_students)
    else:
        active = get_active_session()
        if active:
            stats = get_session_stats(active["id"], total_students)
        else:
            # Overall system stats when no class is active
            stats = {
                "class_id": None,
                "class_name": "No Active Class",
                "subject": "—",
                "date": "—",
                "status": "inactive",
                "present_count": 0,
                "attendance_rate": 0,
                "last_marked": None
            }
            
    stats["total_registered"] = total_students
    stats["camera_running"] = camera.is_running
    return jsonify(stats)


@app.route("/export_csv")
def export_csv():
    class_id = request.args.get("class_id")
    if not class_id:
        return jsonify({"success": False, "message": "Class ID is required to export."}), 400
        
    csv_content = export_session_to_csv(int(class_id))
    filename = f"attendance_class_{class_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


@app.route("/notifications")
def get_notifications():
    since = float(request.args.get("since", 0))
    with _notifications_lock:
        new_notifications = [
            n for n in _recent_notifications
            if n["timestamp"] > since
        ]
    return jsonify({
        "notifications": new_notifications,
        "server_time": time.time()
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "camera_running": camera.is_running,
        "registered_students": len(get_students()),
        "active_session": get_active_session() is not None
    })


if __name__ == "__main__":
    print("=" * 60)
    print("  FalconEye - Classroom Face Recognition Attendance System")
    print("  Starting server at http://localhost:5000")
    print("=" * 60)
    
    count = load_known_faces()
    print(f"[App] Loaded {count} registered face(s)")
    
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True,
        use_reloader=False
    )
