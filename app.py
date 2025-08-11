from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import io
from datetime import datetime
from utils.export_excel import export_to_excel
from werkzeug.utils import secure_filename
from functools import wraps
from flask import abort
import pandas as pd
from utils.analytics_utils import (
    get_status_counts,
    get_overdue_count,
    get_upcoming_count,
    get_task_throughput,
    get_heatmap_data,
    get_leaderboard,
    get_cycle_time_avg,
    get_on_time_percentage,
    get_bottleneck_top_areas
)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'super_secret_flask_key'

# Path to SQLite DB
DB_PATH = 'workorder.db'

# ---------- DB Initialization ----------
def init_database():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Create users table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                profile_pic TEXT
            )
        ''')

        # Create tasks table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                machine_id TEXT,
                area TEXT,
                deadline TEXT,
                assigned_to INTEGER,
                status TEXT,
                FOREIGN KEY (assigned_to) REFERENCES users (id)
            )
        ''')

        # Create messages table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                message TEXT,
                timestamp TEXT,
                task_id INTEGER,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        ''')

        # Create completed tasks archive table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS completed_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                title TEXT,
                description TEXT,
                machine_id TEXT,
                area TEXT,
                deadline TEXT,
                assigned_to INTEGER,
                completed_at TEXT,
                FOREIGN KEY (assigned_to) REFERENCES users (id)
            )
        ''')

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login first.", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash("Access denied. Admins only.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper
# Initialize database
init_database()

# ---------- DB Connection Helper ----------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn# ---------- tiny helper just for analytics ----------
def fetch_scalar(query, args=()):
    """Run a SELECT that returns a single scalar value (like COUNT(*))"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


# ---------------- analytics (compact dashboard) ----------------
@app.route('/analytics')
@admin_required
def analytics():
    status_counts   = get_status_counts()
    overdue_count   = get_overdue_count()
    upcoming_count  = get_upcoming_count(3)
    cycle_time      = get_cycle_time_avg()
    on_time         = get_on_time_percentage()
    throughput      = get_task_throughput(7)
    heatmap_area, heatmap_machine = get_heatmap_data()
    leaderboard     = get_leaderboard(5)
    bottlenecks     = get_bottleneck_top_areas(3)

    return render_template(
        'analytics.html',
        pending_count=status_counts["pending"],
        in_progress_count=status_counts["in_progress"],
        done_count=status_counts["done"],
        overdue_count=overdue_count,
        upcoming_count=upcoming_count,
        cycle_time=cycle_time,
        on_time=on_time,
        throughput=throughput,
        heatmap_area=heatmap_area,
        heatmap_machine=heatmap_machine,
        leaderboard=leaderboard,
        bottlenecks=bottlenecks
    )

@app.route('/')
def home():
    return render_template('home.html')


# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect('/dashboard')
        else:
            flash("Invalid username or password", "danger")
            return redirect('/login')

    return render_template('login.html')


@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d'):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except:
            return value  # fallback if parsing fails
    return value.strftime(format)

#--------------Remove worker---------------
@app.route('/remove_worker/<int:worker_id>', methods=['POST'])
def remove_worker(worker_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Unauthorized access.")
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor()

    # Fetch worker's username before deleting
    cur.execute("SELECT username FROM users WHERE id = ?", (worker_id,))
    worker = cur.fetchone()

    if not worker:
        flash("Worker not found.")
        conn.close()
        return redirect(url_for('worker_list'))

    worker_name = worker['username']

    # Delete all active tasks assigned to this worker
    cur.execute("DELETE FROM tasks WHERE assigned_to = ? AND status != 'Done'", (worker_id,))

    # For completed tasks, set assigned_to = NULL
    cur.execute("UPDATE tasks SET assigned_to = NULL WHERE assigned_to = ? AND status = 'Done'", (worker_id,))

    # Finally, remove the worker
    cur.execute("DELETE FROM users WHERE id = ?", (worker_id,))
    conn.commit()
    conn.close()

    flash(f"🚀 {worker_name} has been removed successfully!")
    return redirect(url_for('workers_list'))


# ---------- REGISTER ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        role = request.form.get('role')

        if not username or not password or not confirm or not role:
            flash("All fields are required", "danger")
            return redirect(url_for('register'))

        if password != confirm:
            flash("Passwords do not match", "danger")
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                        (username, hashed_pw, role))
            conn.commit()
            conn.close()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "danger")
            return redirect(url_for('register'))

    return render_template('register.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ---------- DASHBOARD ----------
from datetime import datetime

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, username, role, profile_pic FROM users WHERE id = ?", (session['user_id'],))
    user = cur.fetchone()

    current_date = datetime.today().date()

    if session.get('role') == 'admin':
        cur.execute("""
            SELECT tasks.*, users.username AS worker_name
            FROM tasks
            LEFT JOIN users ON tasks.assigned_to = users.id
            ORDER BY deadline
        """)
        tasks = cur.fetchall()
        conn.close()
        return render_template('admin_dashboard.html', tasks=tasks, user=user, current_date=current_date)

    cur.execute("""
        SELECT *
        FROM tasks
        WHERE assigned_to = ?
        ORDER BY deadline
    """, (session['user_id'],))
    tasks = cur.fetchall()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS completed_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER UNIQUE,
            title TEXT,
            description TEXT,
            machine_id TEXT,
            area TEXT,
            deadline TEXT,
            worker_id INTEGER,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    cur.execute("""
        SELECT *
        FROM completed_tasks
        WHERE worker_id = ?
        ORDER BY completed_at DESC
    """, (session['user_id'],))
    completed_tasks = cur.fetchall()

    conn.close()
    return render_template('worker_dashboard.html', tasks=tasks, completed_tasks=completed_tasks, user=user)

# ---------- CREATE TASK ----------
@app.route('/task/create', methods=['GET', 'POST'])
def create_task():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        machine_id = request.form['machine_id']
        area = request.form['area']
        deadline = request.form['deadline']
        assigned_to = request.form.get('assigned_to') or None
        status = request.form.get('status', 'Pending')

        cur.execute('''
            INSERT INTO tasks (title, description, machine_id, area, deadline, assigned_to, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, machine_id, area, deadline, assigned_to, status))
        conn.commit()
        flash('Task created successfully!')
        return redirect('/dashboard')

    cur.execute("SELECT id, username FROM users WHERE role='worker'")
    workers = cur.fetchall()
    return render_template('create_task.html', workers=workers)

# ---------- UPDATE TASK STATUS ----------
@app.route('/task/update/<int:task_id>', methods=['POST'])
def update_task(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    new_status = request.form.get('status')
    if not new_status:
        flash("No status provided.", "danger")
        return redirect(url_for('dashboard'))

    conn = get_db()
    cur = conn.cursor()

    # Fetch the task first
    cur.execute("""
        SELECT id, title, description, machine_id, area, deadline, assigned_to, status
        FROM tasks
        WHERE id = ?
    """, (task_id,))
    task = cur.fetchone()

    if not task:
        conn.close()
        flash("Task not found.", "danger")
        return redirect(url_for('dashboard'))

    # Update status
    cur.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))

    # If it's DONE -> archive it (once)
    if new_status == 'Done':
        # Make sure completed_tasks table exists (safe to run every time)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS completed_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER UNIQUE,
                title TEXT,
                description TEXT,
                machine_id TEXT,
                area TEXT,
                deadline TEXT,
                worker_id INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check if already archived
        cur.execute("SELECT 1 FROM completed_tasks WHERE task_id = ?", (task_id,))
        already_there = cur.fetchone()

        if not already_there:
            cur.execute("""
                INSERT INTO completed_tasks
                    (task_id, title, description, machine_id, area, deadline, worker_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                task['id'],
                task['title'],
                task['description'],
                task['machine_id'],
                task['area'],
                task['deadline'],
                task['assigned_to']
            ))

    conn.commit()
    conn.close()

    flash("Status updated successfully.", "success")

    # Redirect by role
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('dashboard'))
    else:
        # assuming your worker dashboard route name is 'dashboard' too.
        # if it's different (e.g. 'worker_dashboard'), change it here:
        return redirect(url_for('dashboard'))

# ---------- DELETE TASK ----------
@app.route('/delete_task/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    flash("Task deleted successfully🚀")
    return redirect('/dashboard')


# ---------- EXPORT ----------
@app.route('/export', methods=['GET'])
def export():
    # Guard: only admins can export
    if 'role' not in session or session['role'] != 'admin':
        flash("You must be an admin to export tasks.", "danger")
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor()

    # Fetch all tasks assigned to registered workers
    cur.execute("""
        SELECT 
            t.id,
            t.title,
            t.description,
            t.machine_id,
            t.area,
            t.deadline,
            t.status,
            u.username  AS worker_name,
            u.email     AS worker_email,
            u.phone     AS worker_phone
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        WHERE u.role = 'worker'
        ORDER BY t.deadline
    """)
    rows = cur.fetchall()
    data = [dict(r) for r in rows]

    if not data:
        flash("No tasks to export.", "info")
        return redirect(url_for('dashboard'))

    # Convert to DataFrame
    df = pd.DataFrame(data)[[
        "title", "description", "machine_id", "area",
        "deadline", "status", "worker_name", "worker_email", "worker_phone"
    ]].rename(columns={
        "title": "Title",
        "description": "Description",
        "machine_id": "Machine ID",
        "area": "Area",
        "deadline": "Deadline",
        "status": "Status",
        "worker_name": "Assigned Worker",
        "worker_email": "Worker Email",
        "worker_phone": "Worker Phone"
    })

    # Add Serial Number column
    df.insert(0, "S.No", range(1, len(df) + 1))

    # Write to Excel in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Tasks")
        ws = writer.sheets["Tasks"]

        # Auto-fit columns
        for idx, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            ws.set_column(idx, idx, max_len)

    output.seek(0)
    filename = f"all_tasks_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    flash("Tasks exported with fresh serial numbers!", "success")

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ---------- WORKERS LIST ----------
@app.route('/admin/workers')
def workers_list():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    workers = conn.execute("SELECT id, username, email, phone FROM users WHERE role='worker'").fetchall()
    conn.close()

    return render_template('workers_list.html', workers=workers, user=user)


# ---------- WORKER DETAIL ----------
@app.route('/admin/worker/<int:worker_id>')
def worker_detail(worker_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = get_db()
    worker = conn.execute("SELECT * FROM users WHERE id=?", (worker_id,)).fetchone()
    tasks = conn.execute("SELECT * FROM tasks WHERE assigned_to=?", (worker_id,)).fetchall()
    conn.close()
    return render_template('worker_detail.html', worker=worker, tasks=tasks)

# ---------- ROUTE: Admins list ----------
@app.route("/admins", methods=["GET"])
@admin_required
def admin_list():
    conn = get_db()
    cur = conn.cursor()

    # Logged-in admin (for navbar avatar)
    cur.execute(
        "SELECT id, username, role, profile_pic FROM users WHERE id = ?",
        (session["user_id"],),
    )
    user = cur.fetchone()

    # Fetch all admins (exclude yourself if you want -> add AND id != ?)
    cur.execute(
        "SELECT id, username, email, phone, profile_pic FROM users WHERE role = 'admin'"
    )
    admins = cur.fetchall()

    return render_template("admin_list.html", admins=admins, user=user)

@app.route('/admins/<int:admin_id>')
@admin_required
def admin_details(admin_id):
    conn = get_db()
    cur = conn.cursor()

    # fetch logged-in admin for navbar avatar
    cur.execute("SELECT id, username, role, profile_pic FROM users WHERE id = ?", (session['user_id'],))
    user = cur.fetchone()

    cur.execute("SELECT id, username, email, phone, role, profile_pic FROM users WHERE id = ? AND role='admin'", (admin_id,))
    admin = cur.fetchone()
    if not admin:
        abort(404)

    return render_template('admin_details.html', admin=admin, user=user)

#--------------------Remove Profile Pic-------------------
@app.route('/remove_profile_pic', methods=['POST'])
def remove_profile_pic():
    if 'user_id' not in session:
        flash("Please log in to modify your profile.", "error")
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()

    # Get the current profile picture
    cur.execute("SELECT profile_pic FROM users WHERE id = ?", (user_id,))
    profile_pic = cur.fetchone()[0]

    if profile_pic:
        # Remove from folder
        file_path = os.path.join('static/uploads', profile_pic)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Remove reference from DB
        cur.execute("UPDATE users SET profile_pic = NULL WHERE id = ?", (user_id,))
        conn.commit()

    flash("Profile picture removed successfully.", "success")
    return redirect(url_for('profile'))

@app.route("/worker_dashboard")
def worker_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE id=?", (session['user_id'],))
    user = dict(cur.fetchone() or {})

    cur.execute("SELECT * FROM tasks WHERE assigned_to=?", (session['user_id'],))
    tasks = [dict(r) for r in cur.fetchall()]

    return render_template("worker_dashboard.html", tasks=tasks, user=user)

# ---------- PROFILE ----------
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash("Please login to view your profile.", "warning")
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = dict(cur.fetchone())

    if request.method == 'POST':
        username = request.form['username']
        phone = request.form['phone']
        email = request.form['email']
        password = request.form['password']
        file = request.files.get('profile_pic')

        profile_pic_filename = user.get("profile_pic")

        # Handle file upload if provided
        if file and file.filename:
            filename = secure_filename(file.filename)
            upload_path = os.path.join('static/uploads', filename)
            file.save(upload_path)
            profile_pic_filename = filename

        # Start building the update query
        update_query = "UPDATE users SET username = ?, phone = ?, email = ?, profile_pic = ?"
        params = [username, phone, email, profile_pic_filename]

        # Add password if provided
        if password:
            hashed_pw = generate_password_hash(password)
            update_query += ", password = ?"
            params.append(hashed_pw)

        update_query += " WHERE id = ?"
        params.append(user_id)

        cur.execute(update_query, tuple(params))
        conn.commit()

        flash("Profile updated successfully!", "success")

        # Reload updated user
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = dict(cur.fetchone())

    completed_tasks = []
    if user['role'] == 'worker':
        cur.execute("SELECT * FROM tasks WHERE assigned_to = ? AND status = 'completed'", (user_id,))
        completed_tasks = cur.fetchall()

    conn.close()
    return render_template('profile.html', user=user, completed_tasks=completed_tasks)

#----------------Admin Profile-------------------
@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():
    if 'user_id' not in session:
        flash("Please login to view your profile.", "warning")
        return redirect('/login')

    if session.get('role') != 'admin':
        flash("You are not allowed to access the admin profile page.", "danger")
        return redirect(url_for('dashboard'))

    user_id = session['user_id']
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = dict(cur.fetchone())

    if request.method == 'POST':
        username = request.form['username']
        phone = request.form['phone']
        email = request.form['email']
        password = request.form['password']
        file = request.files.get('profile_pic')

        profile_pic_filename = user.get("profile_pic")

        # Handle file upload if provided
        if file and file.filename:
            filename = secure_filename(file.filename)
            upload_path = os.path.join('static/uploads', filename)
            file.save(upload_path)
            profile_pic_filename = filename

        # Build update query
        update_query = "UPDATE users SET username = ?, phone = ?, email = ?, profile_pic = ?"
        params = [username, phone, email, profile_pic_filename]

        if password:
            hashed_pw = generate_password_hash(password)
            update_query += ", password = ?"
            params.append(hashed_pw)

        update_query += " WHERE id = ?"
        params.append(user_id)

        cur.execute(update_query, tuple(params))
        conn.commit()

        flash("Admin profile updated successfully!", "success")

        # Reload updated user
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = dict(cur.fetchone())

    conn.close()
    return render_template('profile.html', user=user)
# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(debug=True)
