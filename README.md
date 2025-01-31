## Features

- Proxmox Cluster Management
- Node Draining and Migration
- Update Management
- Resource Monitoring
  - New Dashboard Metric Cards
    - Real-time VM and Container Status
    - Cluster CPU and Memory Usage Overview
- Logging and Tracking

## Dashboard

The dashboard provides a comprehensive view of your Proxmox cluster, featuring:

- Top-level Metric Cards with key cluster statistics
  - Running VMs and Containers
  - Cluster CPU and Memory Usage
- Detailed node status
- VM and container metrics
- Update availability
- Resource allocation

## Testing

### Running Tests

Tests are implemented using pytest and can be run using Docker Compose:

```bash
cd project
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

The test suite includes:
- Authentication tests (registration, login, logout)
- Settings management tests (Proxmox credentials)
- Validation checks
- Login/Logout functionality
- API Integration tests

### Test Environment Variables

The following Jenkins environment variables are used for testing:
- `proxmox_server_test`: Test Proxmox server hostname
- `proxmox_user_test`: Test Proxmox username
- `proxmox_pw_test`: Test Proxmox password

### Troubleshooting Test Imports

If you encounter module import issues:
- An `__init__.py` file has been added to the project directory to mark it as a Python package
- The `PYTHONPATH` is set to `/app` in the Dockerfile to ensure proper module resolution
- Test imports use relative imports from the project root
- Docker Compose test configuration mounts the project at `/app`

### Continuous Integration

Tests are automatically run as part of the Jenkins CI/CD pipeline for each build.

### Deployment

The application is automatically deployed to a local server when all tests pass. The deployment process:

1. Requirements:
   - Docker and Docker Compose installed on target server
   - SSH access to target server
   - Jenkins credentials configured:
     - proxman_server_ip: Target server IP address
     - proxman_user: SSH username
     - proxman_pw: SSH password

2. Deployment Features:
   - Automatic container management
   - Zero-downtime deployment
   - Automatic container restarts on failure
   - Uses latest successful Docker image
   - Maintains application state

3. Deployment Process:
   - Creates deployment directory on target server
   - Copies Docker Compose configuration
   - Pulls latest Docker image
   - Gracefully stops existing containers
   - Starts new containers with updated image
