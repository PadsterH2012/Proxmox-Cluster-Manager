from flask import jsonify, request, session, redirect, current_app
from flask_wtf.csrf import generate_csrf
from csrf import csrf
from models import User, db

def register_routes(app):
    @app.route('/register', methods=['POST'])
    def register():
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Missing username or password'}), 400

        username = data['username'].strip()
        password = data['password'].strip()

        # Validate username
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400

        # Validate password
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        if not any(char.isdigit() for char in password):
            return jsonify({'error': 'Password must contain at least one number'}), 400
        # Special characters are recommended but not required

        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400

        user = User(username=data['username'])
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()

        return jsonify({'message': 'User created successfully'}), 201

    @app.route('/login', methods=['POST'])
    def login():
        print("\n[DEBUG] ===== Login Attempt =====")
        print("[DEBUG] Request headers:", dict(request.headers))
        print("[DEBUG] Request cookies:", dict(request.cookies))
        
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        print("[DEBUG] Login data:", dict(data))

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Missing username or password'}), 400

        user = User.query.filter_by(username=data['username']).first()
        
        if user and user.check_password(data['password']):
            print("[DEBUG] Login successful for user:", user.username)
            session.clear()  # Clear any existing session
            session.permanent = True
            session['user_id'] = user.id
            session['csrf_token'] = generate_csrf()  # Generate new CSRF token
            session.modified = True  # Ensure session is saved
            print("[DEBUG] Session after login:", dict(session))
            print("[DEBUG] Session file path:", current_app.config['SESSION_FILE_DIR'])
            print("[DEBUG] Session cookie name:", current_app.config['SESSION_COOKIE_NAME'])
            print("[DEBUG] New CSRF token:", session['csrf_token'])
            return jsonify({
                'message': 'Logged in successfully',
                'redirect': '/dashboard'
            }), 200
        
        return jsonify({'error': 'Invalid username or password'}), 401

    @app.route('/logout', methods=['GET', 'POST'])
    def logout():
        print("[DEBUG] Logging out user:", session.get('user_id'))
        print("[DEBUG] Session before logout:", dict(session))
        session.clear()  # Clear entire session including CSRF token
        print("[DEBUG] Session after logout:", dict(session))
        return redirect('/')

    @app.route('/protected')
    def protected():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return jsonify({'message': 'This is a protected route'}), 200
