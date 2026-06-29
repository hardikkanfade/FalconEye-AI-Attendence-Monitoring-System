"""
database.py - SQLite database module for class sessions and student profiles.
"""

import sqlite3
import csv
import io
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / "attendance.db"


def get_connection():
    """Get a SQLite database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    
    # 2. Classes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_name TEXT NOT NULL,
            subject TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' -- 'active' or 'completed'
        )
    """)
    
    # 3. Attendance table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            student_id TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Present',
            FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
        )
    """)
    
    # Indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_session 
        ON attendance (class_id, student_id)
    """)
    
    conn.commit()
    conn.close()
    print("[DB] Database schema initialized.")


# ─────────────────────────── STUDENTS CRUD ───────────────────────────

def add_student(student_id: str, name: str) -> dict:
    """Register a new student."""
    student_id = student_id.strip()
    name = name.strip()
    
    if not student_id or not name:
        return {"success": False, "message": "Student ID and Name are required."}
        
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO students (student_id, name, created_at) VALUES (?, ?, ?)",
            (student_id, name, now)
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": f"Student '{name}' registered successfully."}
    except sqlite3.IntegrityError:
        conn.close()
        return {"success": False, "message": f"Student ID '{student_id}' is already registered."}
    except Exception as e:
        conn.close()
        return {"success": False, "message": f"Database error: {str(e)}"}


def get_students(search_query: str = None) -> list:
    """Get all registered students, optionally filtered by name or ID."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if search_query and search_query.strip():
        q = f"%{search_query.strip()}%"
        cursor.execute(
            "SELECT student_id, name, created_at FROM students WHERE student_id LIKE ? OR name LIKE ? ORDER BY name ASC",
            (q, q)
        )
    else:
        cursor.execute("SELECT student_id, name, created_at FROM students ORDER BY name ASC")
        
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_student_by_id(student_id: str) -> dict:
    """Retrieve a student by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, name FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_student(student_id: str) -> bool:
    """Delete a student and cascade delete their attendance records."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


# ─────────────────────────── CLASS SESSIONS ───────────────────────────

def start_class_session(class_name: str, subject: str) -> dict:
    """Start a new class session. Auto-completes any existing active session."""
    class_name = class_name.strip()
    subject = subject.strip()
    
    if not class_name or not subject:
        return {"success": False, "message": "Class Name and Subject are required."}
        
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Auto-complete any active classes
        cursor.execute("UPDATE classes SET status = 'completed' WHERE status = 'active'")
        
        today = date.today().isoformat()
        cursor.execute(
            "INSERT INTO classes (class_name, subject, date, status) VALUES (?, ?, ?, 'active')",
            (class_name, subject, today)
        )
        class_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": f"Session started for {class_name} ({subject}).",
            "class_id": class_id,
            "class_name": class_name,
            "subject": subject
        }
    except Exception as e:
        conn.close()
        return {"success": False, "message": f"Database error: {str(e)}"}


def end_class_session(class_id: int) -> dict:
    """End a class session."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE classes SET status = 'completed' WHERE id = ?", (class_id,))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Class session completed."}
    except Exception as e:
        conn.close()
        return {"success": False, "message": f"Database error: {str(e)}"}


def get_active_session() -> dict:
    """Get the currently active class session if one exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, class_name, subject, date, status FROM classes WHERE status = 'active' LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_class_history() -> list:
    """Get list of all class sessions with total attendance counts."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # We want to know: Class details + count of present students
    cursor.execute("""
        SELECT 
            c.id, c.class_name, c.subject, c.date, c.status,
            (SELECT COUNT(*) FROM attendance a WHERE a.class_id = c.id) as present_count
        FROM classes c
        ORDER BY c.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ─────────────────────────── ATTENDANCE MARKING ───────────────────────────

def mark_student_attendance(class_id: int, student_id: str) -> dict:
    """
    Mark a student present in a class session.
    Only inserts if the student isn't already marked present in this session.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if student exists
        cursor.execute("SELECT name FROM students WHERE student_id = ?", (student_id,))
        student = cursor.fetchone()
        if not student:
            conn.close()
            return {"success": False, "message": f"Student ID '{student_id}' is not registered."}
            
        student_name = student["name"]
        
        # Check if already marked present in this class session
        cursor.execute(
            "SELECT id, time FROM attendance WHERE class_id = ? AND student_id = ?",
            (class_id, student_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return {
                "success": False,
                "already_marked": True,
                "message": f"Attendance already marked for {student_name} today at {existing['time']}"
            }
            
        # Insert attendance record
        now_time = datetime.now().strftime("%H:%M:%S")
        cursor.execute(
            "INSERT INTO attendance (class_id, student_id, time, status) VALUES (?, ?, ?, 'Present')",
            (class_id, student_id, now_time)
        )
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "already_marked": False,
            "message": f"✅ Attendance marked for {student_name}",
            "student_id": student_id,
            "name": student_name,
            "time": now_time
        }
        
    except Exception as e:
        conn.close()
        return {"success": False, "message": f"Database error: {str(e)}"}


def get_attendance_records(class_id: int = None, date_filter: str = None, name_filter: str = None) -> list:
    """Get detailed attendance logs with optional filters."""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            a.id, a.class_id, a.student_id, a.time, a.status,
            s.name as student_name,
            c.class_name, c.subject, c.date as class_date
        FROM attendance a
        JOIN students s ON a.student_id = s.student_id
        JOIN classes c ON a.class_id = c.id
        WHERE 1=1
    """
    params = []
    
    if class_id:
        query += " AND a.class_id = ?"
        params.append(class_id)
        
    if date_filter:
        query += " AND c.date = ?"
        params.append(date_filter)
        
    if name_filter and name_filter.strip():
        query += " AND (s.name LIKE ? OR s.student_id LIKE ?)"
        term = f"%{name_filter.strip()}%"
        params.append(term)
        params.append(term)
        
    query += " ORDER BY c.date DESC, a.time DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_session_stats(class_id: int, total_registered_students: int) -> dict:
    """Get statistics for a specific class session."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Class details
    cursor.execute("SELECT class_name, subject, date, status FROM classes WHERE id = ?", (class_id,))
    class_row = cursor.fetchone()
    if not class_row:
        conn.close()
        return {}
        
    # Present count
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE class_id = ?", (class_id,))
    present_count = cursor.fetchone()["count"]
    
    # Last marked student
    cursor.execute("""
        SELECT s.name, a.time 
        FROM attendance a
        JOIN students s ON a.student_id = s.student_id
        WHERE a.class_id = ?
        ORDER BY a.time DESC LIMIT 1
    """, (class_id,))
    last_row = cursor.fetchone()
    
    last_marked = None
    if last_row:
        last_marked = {"name": last_row["name"], "time": last_row["time"]}
        
    # Rate
    rate = 0
    if total_registered_students > 0:
        rate = round((present_count / total_registered_students) * 100, 1)
        
    conn.close()
    return {
        "class_id": class_id,
        "class_name": class_row["class_name"],
        "subject": class_row["subject"],
        "date": class_row["date"],
        "status": class_row["status"],
        "present_count": present_count,
        "attendance_rate": rate,
        "last_marked": last_marked
    }


def export_session_to_csv(class_id: int) -> str:
    """Export attendance logs for a class to CSV."""
    records = get_attendance_records(class_id=class_id)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Record ID", "Class Name", "Subject", "Date", "Student ID", "Student Name", "Time Marked", "Status"])
    
    for r in records:
        writer.writerow([
            r["id"],
            r["class_name"],
            r["subject"],
            r["class_date"],
            r["student_id"],
            r["student_name"],
            r["time"],
            r["status"]
        ])
        
    return output.getvalue()


# Initialize schema
init_db()
