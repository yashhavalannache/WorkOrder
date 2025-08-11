WprlOrder System ⚙️
The WprkOrder System is a streamlined task and work order management platform designed to simplify operations for admins, workers, and supervisors. It ensures smooth task assignment, tracking, and completion with real-time updates, providing a user-friendly interface and robust backend logic.

✨ Features
User Authentication 🔐
Secure login and registration for admins and workers with role-based access.

Admin Dashboard 📋

Create, update, assign, and delete tasks.

Track task deadlines and status (Pending/Done/In Progress).

Manage workers with ease.

Worker Dashboard 🧑‍🔧

View tasks assigned by the admin.

Update task status to Done when completed.

Status Management 🎨

Color-coded task statuses for quick insights (Pending = Grey, Done = Green, In Progress = Blue).

Flash Messages & Notifications 🔔
Engaging success and error messages for a smooth user experience.

🛠️ Tech Stack
Frontend: HTML5, CSS3, Bootstrap 5

Backend: Python (Flask Framework)

Database: SQLite

Other Tools: Jinja2 Templates, Flask Sessions, Flash Messaging

Folder Structure
Industry Mini Project/
├── app.py
├── README.md
├── requirements.txt
├── workorder.db
├── exported_tasks.xlsx

├── database/
│   ├── industry.db
│   └── workorders.db
│
├── static/
│   ├── profile.css
│   ├── style.css
├── ├── backgrounds/
│   ├── uploads/
│
├── templates/
│   ├── admin_dashboard.html
│   ├── admin_details.html
│   ├── admin_list.html
│   ├── admin_profile.html
│   ├── chat.html
│   ├── create_task.html
│   ├── export_success.html
│   ├── login.html
│   ├── profile.html
│   ├── register.html
│   ├── worker_dashboard.html
│   ├── worker_detail.html
│   └── workers_list.html
│
└── utils/
    ├── __pycache__/
    ├── db_init.py
    └── export_excel.py
