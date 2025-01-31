import pytest
import os
from models import ProxmoxCredentials, db

def test_save_proxmox_credentials(client):
    """Test saving Proxmox credentials to the database"""
    # First login to access settings
    client.post('/register', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    client.post('/login', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })

    # Get test credentials from environment variables
    test_server = os.getenv('proxmox_server_test', 'test-server')
    test_user = os.getenv('proxmox_user_test', 'test-user')
    test_password = os.getenv('proxmox_pw_test', 'test-password')

    # Test saving Proxmox credentials
    response = client.post('/api/settings/proxmox', json={
        'hostname': test_server,
        'username': test_user,
        'password': test_password,
        'port': 8006,
        'verify_ssl': True
    })
    assert response.status_code == 200
    assert 'success' in response.get_json().get('message', '').lower()

    # Verify credentials were saved to database
    credentials = ProxmoxCredentials.query.first()
    assert credentials is not None
    assert credentials.hostname == test_server
    assert credentials.username == test_user
    assert credentials.password == test_password
    assert credentials.port == 8006
    assert credentials.verify_ssl is True

def test_update_proxmox_credentials(client):
    """Test updating existing Proxmox credentials"""
    # First create initial credentials
    test_save_proxmox_credentials(client)

    # Update with new values
    new_port = 8007
    response = client.post('/api/settings/proxmox', json={
        'hostname': os.getenv('proxmox_server_test', 'test-server'),
        'username': os.getenv('proxmox_user_test', 'test-user'),
        'password': os.getenv('proxmox_pw_test', 'test-password'),
        'port': new_port,
        'verify_ssl': False
    })
    assert response.status_code == 200
    assert 'success' in response.get_json().get('message', '').lower()

    # Verify updates were saved
    credentials = ProxmoxCredentials.query.first()
    assert credentials is not None
    assert credentials.port == new_port
    assert credentials.verify_ssl is False

def test_remove_proxmox_credentials(client):
    """Test removing Proxmox credentials"""
    # First create credentials
    test_save_proxmox_credentials(client)

    # Remove credentials by sending empty hostname
    response = client.post('/api/settings/proxmox', json={
        'hostname': '',
        'username': '',
        'password': '',
        'port': 8006,
        'verify_ssl': True
    })
    assert response.status_code == 200
    assert 'removed' in response.get_json().get('message', '').lower()

    # Verify credentials were removed
    credentials = ProxmoxCredentials.query.first()
    assert credentials is None

def test_unauthorized_access(client):
    """Test unauthorized access to settings endpoints"""
    response = client.post('/api/settings/proxmox', json={
        'hostname': 'test',
        'username': 'test',
        'password': 'test'
    })
    assert response.status_code == 401
    assert 'unauthorized' in response.get_json().get('error', '').lower()
