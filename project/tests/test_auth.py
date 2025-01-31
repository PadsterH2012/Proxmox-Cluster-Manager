import pytest
from models import User

def test_registration_success(client):
    """Test successful user registration"""
    response = client.post('/register', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    assert response.status_code == 201
    assert 'User created successfully' in response.get_json()['message']

def test_registration_validation(client):
    """Test registration validation rules"""
    # Test short username
    response = client.post('/register', json={
        'username': 'ab',
        'password': 'Test1234!'
    })
    assert response.status_code == 400
    
    # Test weak password
    response = client.post('/register', json={
        'username': 'testuser',
        'password': 'weak'
    })
    assert response.status_code == 400

def test_login_success(client):
    """Test successful login"""
    # First register a user
    client.post('/register', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    
    # Then try to login
    response = client.post('/login', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    assert response.status_code == 200
    assert 'Logged in successfully' in response.get_json()['message']

def test_logout(client):
    """Test logout functionality"""
    # Register and login first
    client.post('/register', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    client.post('/login', json={
        'username': 'testuser',
        'password': 'Test1234!'
    })
    
    # Test logout
    response = client.get('/logout')
    assert response.status_code == 302  # Redirect status
