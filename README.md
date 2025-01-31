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
docker compose -f docker-compose.test-1-auth.yml up --abort-on-container-exit
docker compose -f docker-compose.test-2-settings.yml up --abort-on-container-exit
```

The test suite includes:
- Authentication tests (registration, login, logout)
- Settings management tests (Proxmox credentials)
- Validation checks
- Login/Logout functionality

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
     - proxman-deploy-credentials: Username/password credential containing:
       - Username: SSH username for target server
       - Password: SSH password for target server
       - Description: Include target server IP in description

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

4. Jenkins Configuration:
   - Add a Username with password credential in Jenkins:
     1. Go to Jenkins > Manage Jenkins > Credentials
     2. Click on (global) under Stores scoped to Jenkins
     3. Click Add Credentials
     4. Select Username with password
     5. Set ID as 'proxman-deploy-credentials'
     6. Enter SSH username and password
     7. Add server IP to the description
