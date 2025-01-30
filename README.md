# Proxmox-Cluster-Manager# Proxmox Monitoring Dashboard

A modern web application for monitoring Proxmox VE clusters with real-time metrics collection and visualization.

## Features

### Dashboard
- Real-time cluster overview with auto-refresh every 30 seconds
- Total VMs and Containers count
- Cluster-wide CPU and Memory usage averages
- Node-level monitoring:
  - Status indicators (healthy/warning)
  - CPU and Memory usage with visual progress bars
  - Warning indicators for high resource usage (>80%)
  - IP address tracking for each node
  - System update status:
    - Update availability indicator
    - Number of pending updates
    - Reboot requirement status
- Comprehensive logging system:
  - General Logs: System-wide metrics and events
  - Migration Logs: VM/Container migration events
  - Resource Manager Logs: Resource allocation events
  - Updates Log: System update events
  - Log level filtering (Info/Warn/Critical)

### Metrics Collection
- Automatic collection every 30 seconds
- Immediate collection after saving credentials
- Metrics stored in PostgreSQL database
- Tracked metrics include:
  - Host metrics (CPU, Memory, Disk usage)
  - VM metrics (status, CPU, Memory usage)
  - Container metrics (status, CPU, Memory usage)
- Consolidated metrics logging:
  - Single INFO level log entry for all metrics
  - Format: "Gathering metrics for - X Hosts, Y VMs, Z Containers"
  - Displayed in General Logs section of dashboard

### Update Management
- Automatic update checking for all cluster nodes
- Uses Proxmox credentials for SSH authentication
- Features:
  - Package list update (apt update)
  - Update availability detection
  - Reboot requirement checking
  - Update scheduling capability
- Comprehensive logging:
  - Update check status
  - Number of available updates
  - Reboot requirement status
  - Update process progress

### Settings
- Tabbed interface for better organization:
  - Proxmox Connection: Host configuration and authentication
  - Maintenance Settings: Update intervals and migration settings
  - Backup & Restore Config: Configuration management
- Username/password authentication for Proxmox access
- SSL verification toggle for secure connections
- Credentials securely stored in database
- Connection testing before saving
- Credentials used for both Proxmox API and SSH authentication
- Maintenance settings:
  - Update check interval configuration
  - Metrics collection interval adjustment
  - Automatic VM migration toggle
- Configuration management:
  - Export current settings as JSON backup
  - Import settings from backup file
  - Automatic validation of backup files

## API Endpoints

### Authentication
- `POST /login` - User login
- `POST /register` - User registration
- `GET /logout` - User logout

### Metrics
- `GET /api/metrics/hosts` - Get host metrics
- `GET /api/metrics/vms` - Get VM metrics
- `GET /api/metrics/containers` - Get container metrics
- `POST /api/collect-metrics` - Trigger manual metrics collection

### Updates
- `POST /api/updates/check` - Trigger update check for all nodes
- `POST /api/updates/schedule` - Schedule system updates
- `GET /api/updates/status/<id>` - Get update schedule status

### Logs
- `GET /api/logs` - Get system logs
- `POST /api/logs` - Create new log entry

### Settings
- `GET /settings` - View settings page
- `POST /settings/proxmox` - Update Proxmox credentials

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd project
```

2. Configure environment variables:
```bash
# Database configuration
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Flask configuration
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key
```

3. Build and run with Docker Compose:
```bash
docker compose up --build
```

4. Access the application:
- Dashboard: http://localhost:5000/
- Settings: http://localhost:5000/settings

## Database Schema

### ProxmoxCredentials
- id: Primary key
- host: Proxmox host address
- port: Proxmox port (default: 8006)
- username: Proxmox username (for API and SSH access)
- password: Encrypted password
- verify_ssl: SSL verification flag
- created_at: Creation timestamp
- updated_at: Last update timestamp

### NodeUpdateStatus
- id: Primary key
- node_name: Host node name
- updates_available: Number of available updates
- reboot_required: Whether system reboot is needed
- last_checked: Last update check timestamp

### HostMetrics
- id: Primary key
- node_name: Host node name
- ip_address: Node IP address
- cpu_usage: CPU usage percentage
- memory_usage: Memory usage percentage
- disk_usage: Disk usage percentage
- uptime: Node uptime in seconds
- timestamp: Collection timestamp

### VMMetrics
- id: Primary key
- node_name: Host node name
- vmid: VM identifier
- name: VM name
- status: VM status
- cpu_usage: CPU usage percentage
- memory_usage: Memory usage percentage
- disk_usage: Disk usage percentage
- timestamp: Collection timestamp

### ContainerMetrics
- id: Primary key
- node_name: Host node name
- container_id: Container identifier
- name: Container name
- status: Container status
- cpu_usage: CPU usage percentage
- memory_usage: Memory usage percentage
- disk_usage: Disk usage percentage
- timestamp: Collection timestamp

### DashboardLog
- id: Primary key
- node_name: Related node name (optional)
- action: Log message/description
- status: Log level (info/warning/error)
- created_at: Log timestamp
- details: Additional log details (optional)

### UpdateSchedule
- id: Primary key
- node_name: Target node name
- scheduled_time: When to perform the update
- status: Current status (scheduled/in_progress/completed/failed)
- created_at: Schedule creation time
- completed_at: Update completion time
- error_message: Error details if failed

## Development

### Project Structure
```
project/
├── app.py              # Main application file
├── templates/          # HTML templates
│   ├── dashboard.html  # Dashboard template
│   ├── index.html     # Login/Register page
│   └── settings.html  # Settings page
├── static/            # Static assets
│   └── css/          # CSS stylesheets
├── Dockerfile        # Container configuration
└── docker-compose.yml # Service orchestration
```

### Key Components
1. **Metrics Collection**
   - Background scheduler runs every 30 seconds
   - Proxmox API interaction via proxmoxer
   - Automatic error handling and retry logic
   - Consolidated metrics logging in INFO level

2. **Update Management**
   - Automatic update checking for nodes
   - SSH authentication using Proxmox credentials
   - Package list updates and upgrade scheduling
   - Reboot requirement detection
   - Detailed update logging

3. **Database Management**
   - SQLAlchemy ORM for database operations
   - Automatic table creation and migrations
   - Connection pooling and retry mechanism

4. **Frontend**
   - Modern, responsive design
   - Real-time updates via auto-refresh
   - Loading states for better UX
   - Warning indicators for critical states
   - Sectioned log display with filtering

5. **Logging System**
   - Centralized logging with categorized sections
   - Log level filtering (Info/Warn/Critical)
   - Real-time log updates
   - Consolidated metrics reporting
   - Automatic log rotation (24-hour retention)

## Security

- Password hashing using Werkzeug security
- Session-based authentication
- Protected API endpoints
- SSL verification option for Proxmox connection
- Secure credential storage
- Secure SSH authentication using Proxmox credentials

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
