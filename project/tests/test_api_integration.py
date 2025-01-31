import pytest
import os
from models import ProxmoxCredentials, db, DashboardLog

def test_full_integration_flow(client):
    """Test complete flow from auth through API data collection"""
    # Step 1: Register and login
    client.post('/register', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    login_response = client.post('/login', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    assert login_response.status_code == 200
    assert 'success' in login_response.get_json().get('message', '').lower()

    # Step 2: Configure Proxmox settings
    test_server = os.getenv('proxmox_server_test')
    test_user = os.getenv('proxmox_user_test')
    test_password = os.getenv('proxmox_pw_test')

    print(f"\n[DEBUG] Environment variables:")
    print(f"[DEBUG] proxmox_server_test: {test_server}")
    print(f"[DEBUG] proxmox_user_test: {test_user}")
    print(f"[DEBUG] proxmox_pw_test: {'*' * len(test_password) if test_password else 'Not set'}")

    if not all([test_server, test_user, test_password]):
        pytest.skip("Required environment variables not set")

    settings_response = client.post('/api/settings/proxmox', json={
        'hostname': test_server,
        'username': test_user,
        'password': test_password,
        'port': 8006,
        'verify_ssl': False
    })
    assert settings_response.status_code == 200
    assert 'success' in settings_response.get_json().get('message', '').lower()

    # Step 3: Verify settings were saved
    credentials = ProxmoxCredentials.query.first()
    assert credentials is not None
    assert credentials.hostname == test_server
    assert credentials.username == test_user
    assert credentials.verify_ssl is False

    # Step 4: Check connection status
    connection_response = client.get('/api/connection-status')
    assert connection_response.status_code == 200
    connection_data = connection_response.get_json()
    assert connection_data.get('connected') is True
    assert connection_data.get('auth_type') == 'Password Auth'

    # Step 5: Verify log collection is working
    # Wait briefly for initial log collection
    import time
    time.sleep(5)  # Give time for logs to be collected

    # Check for dashboard logs
    logs = DashboardLog.query.all()
    assert len(logs) > 0, "No logs were collected"
    
    # Verify log content
    log_found = False
    for log in logs:
        if "Metrics collection" in log.action:
            log_found = True
            assert log.status in ['info', 'success'], f"Log status was {log.status}"
            break
    
    assert log_found, "No metrics collection logs found"

def test_api_unauthorized_access(client):
    """Test API endpoints require authentication"""
    # Test connection status endpoint
    response = client.get('/api/connection-status')
    assert response.status_code == 401
    assert 'unauthorized' in response.get_json().get('error', '').lower()

def test_api_invalid_credentials(client):
    """Test API behavior with invalid Proxmox credentials"""
    # First login
    client.post('/register', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    client.post('/login', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })

    # Try to configure with invalid credentials
    response = client.post('/api/settings/proxmox', json={
        'hostname': 'invalid-server',
        'username': 'invalid-user',
        'password': 'invalid-password',
        'port': 8006,
        'verify_ssl': False
    })
    assert response.status_code == 200  # Settings save should succeed

    # Check connection status
    connection_response = client.get('/api/connection-status')
    assert connection_response.status_code == 200
    connection_data = connection_response.get_json()
    assert connection_data.get('connected') is False
    assert 'error' in connection_data
