# 🦅 FalconEye - Classroom Face Recognition Attendance System

**FalconEye** is a modern, real-time Face Recognition Attendance System built with a Python (Flask) backend and a sleek, dark-themed HTML5/CSS3/JS single-page frontend. It is designed for school and university classrooms where teachers can manage attendance sessions and students are automatically checked in via face recognition.

---

## ⚡ Key Features

1. **Classroom Sessions**: Teachers (Admins) can start a named class session (e.g., *CS-301 - Algorithms*). The camera feed automatically activates and begins monitoring attendance.
2. **Pre-registered Students**: Students are pre-registered with their **Student ID / Roll Number**, Name, and face image.
3. **Automated Attendance**: Once a class session is active, the background camera thread auto-detects faces, matches them against registered student profiles, and logs them as "Present" with a real-time timestamp. Includes a 60-second anti-spam cooldown.
4. **Conflict-Free Snapshot Capture**: Resolves the common webcam lock issue. Instead of using browser-side camera APIs (which fail if the backend is already streaming), FalconEye grabs raw frames directly from the backend camera thread and sends them to the client for instant student registration.
5. **Session History & CSV Export**: Allows teachers to view past sessions, review attendance rates, and download comprehensive logs as a CSV file.
6. **Dual Mode Execution**: Automatically falls back to a high-speed OpenCV Haar Cascade face detector if the dlib-based `face_recognition` library is not installed, allowing the system to run out-of-the-box on any machine.

---

## 📁 Project Structure

```text
falcon_eye/
├── app.py                  # Main Flask server (API routes, polling, session controls)
├── face_engine.py          # Face encoding, registration, and recognition (dlib or Haar Cascade)
├── database.py             # SQLite setup and student/class/attendance CRUD
├── camera.py               # Singleton OpenCV camera stream and frame annotator
├── requirements.txt        # Python dependencies
├── .gitignore              # Configured for clean GitHub commits
├── known_faces/            # Folder storing registered student face photographs
│   └── .gitkeep
├── templates/
│   └── index.html          # Modern, tabbed single-page UI
└── static/
    ├── style.css           # Custom dark theme stylesheet (deep-navy & teal)
    └── script.js           # Frontend logic (AJAX, polling, snapshots, tab management)
```

---

## 🛠️ Setup Instructions

### 1. Prerequisites (For Face Recognition Model)
FalconEye uses the `face_recognition` library which relies on `dlib`. Building `dlib` requires a C++ compiler and CMake.

#### Windows:
1. Download and install [CMake](https://cmake.org/download/). Check the option to add CMake to your system PATH.
2. Install Visual Studio (Community Edition is free) and select the **Desktop development with C++** workload.
3. Open terminal/PowerShell and install:
   ```bash
   pip install cmake
   pip install dlib
   ```
   *(If you skip this step, FalconEye will automatically run in **Haar Cascade simulation mode**, which does not require compiling dlib).*

#### macOS:
```bash
brew install cmake
pip install dlib
```

#### Linux (Debian/Ubuntu):
```bash
sudo apt-get update
sudo apt-get install build-essential cmake gfortran git wget curl
sudo apt-get install libgraphicsmagick1-dev libatlas-base-dev
pip install dlib
```

---

## 🚀 Installation & Running

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/falcon-eye.git
   cd falcon-eye
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start the application:
   ```bash
   python app.py
   ```

4. Open your browser and navigate to:
   [http://localhost:5000](http://localhost:5000)

---

## 📝 How to Use

1. **Register Students**:
   - Go to the **Student Registry** tab.
   - Enter a Roll Number/Student ID and the student's name.
   - Drag & drop a photo, browse for a file, or click **Capture from Live Feed** (grabs the frame currently seen by the camera).
   - Click **Register Student**.
2. **Start Class**:
   - Go to the **Live Session** tab.
   - Enter the Class name and Subject.
   - Click **Start Attendance Session**.
3. **Automated Marking**:
   - As students stand in front of the camera, their names will be annotated on the screen in a green box.
   - They will instantly be marked present, and a success toast will slide in.
4. **Review & Export**:
   - Once the class ends, click **End Class Session**.
   - Go to the **Session History** tab, select the class, and click **Export CSV** to download the attendance log.
