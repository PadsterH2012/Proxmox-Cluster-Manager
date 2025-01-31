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
- Authentication tests
- Validation checks
- Login/Logout functionality

### Troubleshooting Test Imports

If you encounter module import issues:
- An `__init__.py` file has been added to the project directory to mark it as a Python package
- The `PYTHONPATH` is set to `/app:/app/project` in the Dockerfile to ensure proper module resolution
- Test imports now use `from project.app import app` instead of `from app import app`
- Docker Compose test configuration updated to mount the entire project and use correct test path

### Continuous Integration

Tests are automatically run as part of the Jenkins CI/CD pipeline for each build.
