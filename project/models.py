from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import requests
from proxmoxer import ProxmoxAPI
import time
from sqlalchemy.exc import OperationalError

db = SQLAlchemy()

def init_db(app):
    """Create tables with retry mechanism"""
    retries = 5
    while retries > 0:
        try:
            with app.app_context():
                db.create_all()
                return
        except OperationalError:
            retries -= 1
            print(f"Database connection failed. Retrying... ({retries} attempts left)")
            time.sleep(5)
    
    raise Exception("Could not connect to database after multiple attempts")

class ProxmoxCredentials(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(255), nullable=False)
    username = db.Column(db.String(255), nullable=True)
    password = db.Column(db.String(255), nullable=True)
    port = db.Column(db.Integer, default=8006)
    verify_ssl = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_proxmox_connection(self):
        verify = self.verify_ssl
        if not verify:
            requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        
        try:
            proxmox = ProxmoxAPI(
                self.hostname,
                user=self.username,
                password=self.password,
                verify_ssl=verify,
                port=self.port
            )
            
            # Test connection
            nodes = proxmox.nodes.get()
            print(f"[DEBUG] Successfully connected! Found {len(nodes)} nodes")
            return proxmox
        except Exception as e:
            print(f"[ERROR] Failed to connect: {str(e)}")
            raise

class NodeUpdateStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(255), nullable=False)
    updates_available = db.Column(db.Integer, default=0)
    reboot_required = db.Column(db.Boolean, default=False)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)

class HostMetrics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(255))
    cpu_usage = db.Column(db.Float)
    cpu_cores = db.Column(db.Integer)
    memory_usage = db.Column(db.Float)
    memory_total = db.Column(db.BigInteger)  # Store in bytes
    disk_usage = db.Column(db.Float)
    uptime = db.Column(db.Integer)  # Store in seconds for precise tracking
    uptime_formatted = db.Column(db.String(255))  # Human readable format
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ClusterMetrics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_cpu = db.Column(db.Float)
    used_cpu = db.Column(db.Float)
    total_memory = db.Column(db.Float)
    used_memory = db.Column(db.Float)
    total_disk = db.Column(db.Float)
    used_disk = db.Column(db.Float)
    node_count = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class VMMetrics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(255), nullable=False)
    vmid = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(255))
    status = db.Column(db.String(50))
    cpu_usage = db.Column(db.Float)
    memory_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ContainerMetrics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(255), nullable=False)
    container_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(255))
    status = db.Column(db.String(50))
    cpu_usage = db.Column(db.Float)
    memory_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class DashboardLog(db.Model):
    __tablename__ = 'dashboard_log'
    
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(255), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='info')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)

    def __repr__(self):
        return f'<DashboardLog {self.id}: {self.action}>'

class UpdateSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(255), nullable=True)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default='scheduled')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

class BalanceSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    balance_mode = db.Column(db.String(50), default='threshold')
    load_threshold = db.Column(db.Integer, default=70)
    min_load_diff = db.Column(db.Integer, default=10)
    check_interval = db.Column(db.Integer, default=300)
    max_concurrent = db.Column(db.Integer, default=2)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UpdateSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    maintenance_window = db.Column(db.String(5))  # Store as HH:MM
    auto_migrate = db.Column(db.Boolean, default=True)
    rolling_update = db.Column(db.Boolean, default=True)
    update_retry = db.Column(db.Integer, default=3)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DrainedVM(db.Model):
    """Track VMs and containers that were shutdown during drain operations"""
    id = db.Column(db.Integer, primary_key=True)
    node_name = db.Column(db.String(255), nullable=False)
    vmid = db.Column(db.Integer, nullable=False)
    vm_type = db.Column(db.String(10), nullable=False)  # 'qemu' or 'lxc'
    name = db.Column(db.String(255))
    drain_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='shutdown')  # shutdown, started, failed
    error_message = db.Column(db.Text)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
