# 🚀 Smart Exam Platform Backend (MCQ + Practical VM Evaluation)

A **production-grade hybrid examination platform** that supports:

* 📝 MCQ Exams (Django)
* 💻 Practical Exams with VM Execution (FastAPI)
* 🧠 Intelligent Evaluation System
* 🏢 Enterprise-ready architecture using MSSQL

---

# 🧠 System Architecture

```text
                ┌────────────────────┐
                │     Frontend       │ (React)
                └─────────┬──────────┘
                          │ API Calls
        ┌─────────────────┴─────────────────┐
        │                                   │
 ┌───────────────┐                  ┌────────────────────┐
 │    Django     │                  │      FastAPI       │
 │ (Core System) │                  │   (VM Controller)  │
 └──────┬────────┘                  └─────────┬──────────┘
        │                                    │
        │                                    │ SSH / VM
        │                             ┌──────────────┐
        │                             │   Vagrant VM │
        │                             │  (Student)   │
        │                             └──────────────┘
        │
        └──────────────┬──────────────┘
                       │
                ┌──────────────┐
                │   MSSQL DB   │
                └──────────────┘
```

---

# ⚙️ Tech Stack

## 🔷 Core Backend

* Django
* Django REST Framework

## ⚡ Practical Engine

* FastAPI
* Paramiko (SSH execution)
* Vagrant VM

## 🗄 Database

* MSSQL (Production)
* SQLite (Development)

---

# 🎯 Key Features

## 👨‍🎓 Student System (Django)

* User registration & login
* Profile management
* Exam enrollment

## 📝 MCQ Exam Engine (Django)

* Create exams
* Add questions
* Auto evaluation
* Instant results

## 💻 Practical Exam Engine (FastAPI)

✔ Auto VM creation
✔ Script execution inside VM
✔ Real-time scoring
✔ Secure isolated environment

---

# ⚡ FastAPI VM Engine (Core Highlight)

Your FastAPI service handles:

## 🔹 1. Start VM

```http
POST /vm/start
```

* Creates VM
* Runs init script
* Returns VM name

---

## 🔹 2. Check Status

```http
GET /vm/status/{vm_name}
```

* starting / running / failed

---

## 🔹 3. Verify Practical Exam

```http
POST /vm/verify
```

* Executes student script inside VM
* Extracts score automatically

✔ Uses:

* SSH (Paramiko)
* Script injection
* Output parsing (`FINAL_SCORE`)

---

## 🔹 4. Destroy VM

```http
POST /vm/destroy
```

* Stops VM
* Cleans resources

---

# 🔥 Practical Exam Flow

```text
Student starts practical exam
        ↓
Django calls FastAPI (/vm/start)
        ↓
VM is created
        ↓
Student writes code
        ↓
Django sends script → FastAPI (/vm/verify)
        ↓
Script runs inside VM
        ↓
Score returned
        ↓
Saved in MSSQL
```

---

# 📂 Project Structure

```text
MCQBACKEND/
│
├── mcqbackend/        # Django config
├── mcqapp/            # MCQ logic
├── practicalapp/      # Practical exam logic
│
├── fastapi-vm/        # VM engine (FastAPI)
│   ├── main.py
│   ├── vagrant_vm.py
│
├── media/
├── static/
│
├── manage.py
└── requirement.txt
```

---

# ⚙️ Setup Instructions

## 1️⃣ Django Setup

```bash
python -m venv venv
venv\Scripts\activate

pip install -r requirement.txt

python manage.py migrate
daphne mcqbackend.asgi:application --port 8000


```

---

## 2️⃣ FastAPI Setup

```bash
cd fastapi-vm

pip install fastapi uvicorn paramiko

uvicorn main:app --reload --port 8001
```

---

# 🗄 MSSQL Database Configuration

Install:

```bash
pip install mssql-django
```

### settings.py

```python
DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': 'exam_db',
        'USER': 'your_user',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
        },
    },
}
```

---

# 🔐 Security Features

* Token-based authentication
* VM isolation (per student)
* No direct system access
* Script sandboxing

---

# 📊 Why This Project is Powerful 🔥

✔ Hybrid Architecture (Django + FastAPI)
✔ Real-world practical exam system
✔ VM-based execution (VERY advanced)
✔ Enterprise database (MSSQL)
✔ Scalable & modular design

---

# 🔮 Future Improvements

* AI cheating detection
* Live monitoring via WebSockets
* Kubernetes scaling
* Code plagiarism detection

---

# 👨‍💻 Author

Faizan Qureshi
Full Stack Developer | Cloud Engineer

---

# 📄 License

MIT License
