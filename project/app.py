from flask import Flask, request, session, jsonify
from flask_wtf.csrf import generate_csrf
from csrf import csrf
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from sqlalchemy.exc import OperationalError
from apscheduler.schedulers.background import BackgroundScheduler
import os
import time
from models import db
from utils.metrics_collector import collect_metrics_job
from utils.node_updater import check_all_nodes_updates
from routes import auth, dashboard, settings, updates

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this in production
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_NAME'] = 'proxmox_dashboard_session'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.config['SESSION_FILE_THRESHOLD'] = 500  # Maximum number of session files
app.config['SESSION_COOKIE_DOMAIN'] = None  # Accept all domains
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # Refresh session on each request

# Initialize extensions
Session(app)

# Configure CSRF protection
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_CHECK_DEFAULT'] = True
app.config['WTF_CSRF_METHODS'] = ['POST', 'PUT', 'PATCH', 'DELETE']
app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['WTF_CSRF_SSL_STRICT'] = False

csrf.init_app(app)

@app.after_request
def add_csrf_token(response):
    if 'text/html' in response.headers.get('Content-Type', ''):
        token = generate_csrf()
        response.set_cookie('csrf_token', token)
        print("[DEBUG] Generated CSRF token:", token)
    return response

db.init_app(app)

# Create tables with retry mechanism
retries = 5
while retries > 0:
    try:
        with app.app_context():
            # Create tables if they don't exist
            db.create_all()
            
            # Verify tables were created
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print("\n[DEBUG] Database tables created:", tables)
            if 'dashboard_log' not in tables:
                print("[ERROR] dashboard_log table not found!")
            else:
                print("[DEBUG] dashboard_log table found")
            break
    except OperationalError as e:
        retries -= 1
        print(f"Database connection failed: {str(e)}")
        print(f"Retrying... ({retries} attempts left)")
        time.sleep(5)

if retries == 0:
    raise Exception("Could not connect to database after multiple attempts")

# Initialize scheduler and jobs
scheduler = BackgroundScheduler()

def run_metrics_job():
    try:
        print("[Scheduler] Running scheduled metrics collection...")
        with app.app_context():
            collect_metrics_job()
        print("[Scheduler] Scheduled metrics collection completed")
    except Exception as e:
        print(f"[Scheduler] Error during scheduled metrics collection: {str(e)}")

def run_updates_check():
    with app.app_context():
        check_all_nodes_updates()

scheduler.add_job(func=run_metrics_job, trigger="interval", seconds=30)  # Run every 30 seconds
scheduler.add_job(func=run_updates_check, trigger="interval", hours=24)
scheduler.start()
print("[Scheduler] Started background jobs")

# Run metrics collection immediately
try:
    print("[Scheduler] Running initial metrics collection...")
    with app.app_context():
        collect_metrics_job()
    print("[Scheduler] Initial metrics collection completed")
except Exception as e:
    print(f"[Scheduler] Error during initial metrics collection: {str(e)}")

# Add before request handler
@app.before_request
def before_request():
    print("\n[DEBUG] ===== Request Start =====")
    print("[DEBUG] Request path:", request.path)
    print("[DEBUG] Session ID:", session.get('_id', None))
    print("[DEBUG] User ID:", session.get('user_id', None))
    print("[DEBUG] Session data:", dict(session))

# Register routes
auth.register_routes(app)
dashboard.register_routes(app)
settings.register_routes(app)
updates.register_routes(app)

# Shut down the scheduler when the app exits
import atexit
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
