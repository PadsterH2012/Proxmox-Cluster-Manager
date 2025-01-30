import re
import json
from flask import render_template, jsonify, request, session, redirect, current_app
from models import ProxmoxCredentials, BalanceSettings, UpdateSettings, db
from utils.metrics_collector import collect_metrics_job

def register_routes(app):
    @app.route('/api/connection-status')
    def connection_status():
        if 'user_id' not in session:
            response = jsonify({'error': 'Unauthorized'})
            response.headers['Content-Type'] = 'application/json'
            return response, 401
            
        credentials = ProxmoxCredentials.query.first()
        if not credentials:
            return jsonify({
                'connected': False,
                'auth_type': 'No Credentials'
            })
            
        try:
            proxmox = credentials.get_proxmox_connection()
            proxmox.nodes.get()  # Test connection
            
            return jsonify({
                'connected': True,
                'auth_type': 'Password Auth'
            })
        except Exception as e:
            return jsonify({
                'connected': False,
                'auth_type': 'Password Auth',
                'error': str(e)
            })

    @app.route('/settings')
    def settings():
        print("\n[DEBUG] ===== Settings Page Access =====")
        print("[DEBUG] Session:", dict(session))
        print("[DEBUG] User ID in session:", session.get('user_id'))
        
        if 'user_id' not in session:
            print("[DEBUG] No user_id in session, redirecting to login")
            return redirect('/')
        
        credentials = ProxmoxCredentials.query.first()
        balance_settings = BalanceSettings.query.first()
        update_settings = UpdateSettings.query.first()
        
        # Create default settings if they don't exist
        if not balance_settings:
            balance_settings = BalanceSettings()
            db.session.add(balance_settings)
            db.session.commit()
            
        if not update_settings:
            update_settings = UpdateSettings()
            db.session.add(update_settings)
            db.session.commit()
        
        return render_template('settings.html', 
                             credentials=credentials,
                             balance_settings=balance_settings,
                             update_settings=update_settings)

    @app.route('/settings/balance', methods=['POST'])
    def update_balance_settings():
        print("\n[DEBUG] ===== Balance Settings Update =====")
        print("[DEBUG] Session:", dict(session))
        print("[DEBUG] User ID in session:", session.get('user_id'))
        print("[DEBUG] Request headers:", dict(request.headers))
        print("[DEBUG] CSRF Token:", request.headers.get('X-CSRFToken'))
        
        if 'user_id' not in session:
            response = jsonify({'error': 'Unauthorized'})
            response.headers['Content-Type'] = 'application/json'
            return response, 401

        try:
            data = request.get_json()
            print("\n[DEBUG] Received request data:", data)
            if data is None:
                error_msg = 'Invalid JSON data'
                print(f"[ERROR] {error_msg}")
                response = jsonify({'error': error_msg})
                response.headers['Content-Type'] = 'application/json'
                return response, 400

            required_fields = ['balance_mode', 'load_threshold', 'min_load_diff', 
                             'check_interval', 'max_concurrent']
            
            if not all(field in data for field in required_fields):
                response = jsonify({'error': 'Missing required fields'})
                response.headers['Content-Type'] = 'application/json'
                return response, 400

            settings = BalanceSettings.query.first()
            if not settings:
                settings = BalanceSettings()
                db.session.add(settings)

            settings.balance_mode = data['balance_mode']
            settings.load_threshold = data['load_threshold']
            settings.min_load_diff = data['min_load_diff']
            settings.check_interval = data['check_interval']
            settings.max_concurrent = data['max_concurrent']

            db.session.commit()
            response = jsonify({'message': 'Balance settings updated successfully'})
            response.headers['Content-Type'] = 'application/json'
            return response, 200
        except Exception as e:
            db.session.rollback()
            response = jsonify({'error': f'Failed to update balance settings: {str(e)}'})
            response.headers['Content-Type'] = 'application/json'
            return response, 400

    @app.route('/settings/update', methods=['POST'])
    def update_update_settings():
        print("\n[DEBUG] ===== Update Settings Update =====")
        print("[DEBUG] Session:", dict(session))
        print("[DEBUG] User ID in session:", session.get('user_id'))
        print("[DEBUG] Request headers:", dict(request.headers))
        print("[DEBUG] CSRF Token:", request.headers.get('X-CSRFToken'))
        
        if 'user_id' not in session:
            response = jsonify({'error': 'Unauthorized'})
            response.headers['Content-Type'] = 'application/json'
            return response, 401

        try:
            data = request.get_json()
            print("\n[DEBUG] Raw request data:", request.get_data(as_text=True))
            print("[DEBUG] Parsed JSON data:", data)
            if data is None:
                error_msg = 'Invalid JSON data'
                print(f"[ERROR] {error_msg}")
                response = jsonify({'error': error_msg})
                response.headers['Content-Type'] = 'application/json'
                return response, 400

            required_fields = ['maintenance_window', 'auto_migrate', 
                             'rolling_update', 'update_retry']
            
            if not all(field in data for field in required_fields):
                response = jsonify({'error': 'Missing required fields'})
                response.headers['Content-Type'] = 'application/json'
                return response, 400

            settings = UpdateSettings.query.first()
            if not settings:
                settings = UpdateSettings()
                db.session.add(settings)

            # Validate maintenance_window format (HH:mm)
            maintenance_window = data['maintenance_window']
            if maintenance_window and not maintenance_window.strip():
                maintenance_window = None
            elif maintenance_window and not re.match(r'^\d{2}:\d{2}$', maintenance_window):
                response = jsonify({'error': 'Invalid maintenance window format. Use HH:mm'})
                response.headers['Content-Type'] = 'application/json'
                return response, 400

            settings.maintenance_window = maintenance_window
            settings.auto_migrate = data['auto_migrate']
            settings.rolling_update = data['rolling_update']
            settings.update_retry = data['update_retry']

            db.session.commit()
            response = jsonify({'message': 'Update settings saved successfully'})
            response.headers['Content-Type'] = 'application/json'
            return response, 200
        except Exception as e:
            db.session.rollback()
            response = jsonify({'error': f'Failed to save update settings: {str(e)}'})
            response.headers['Content-Type'] = 'application/json'
            return response, 400

    @app.route('/api/settings/proxmox', methods=['POST'])
    def update_proxmox_settings():
        print("\n[DEBUG] ===== Proxmox Settings Update =====")
        print("[DEBUG] Session:", dict(session))
        print("[DEBUG] User ID in session:", session.get('user_id'))
        print("[DEBUG] Request headers:", dict(request.headers))
        print("[DEBUG] Request cookies:", dict(request.cookies))
        print("[DEBUG] CSRF Token in headers:", request.headers.get('X-CSRFToken'))
        print("[DEBUG] CSRF Token in form:", request.form.get('csrf_token'))
        print("[DEBUG] Session file path:", current_app.config['SESSION_FILE_DIR'])
        print("[DEBUG] Session cookie name:", current_app.config['SESSION_COOKIE_NAME'])
        
        if 'user_id' not in session:
            print("[DEBUG] No user_id in session")
            response = jsonify({'error': 'Unauthorized - Please log in'})
            response.headers['Content-Type'] = 'application/json'
            return response, 401

        try:
            data = request.get_json()
            print("[DEBUG] Raw request data:", request.get_data(as_text=True))
            print("[DEBUG] Parsed JSON data:", data)
            if data is None:
                response = jsonify({'error': 'Invalid JSON data'})
                response.headers['Content-Type'] = 'application/json'
                return response, 400

            # Delete existing credentials if hostname is empty
            if not data.get('hostname'):
                print("[DEBUG] No hostname provided, removing existing credentials")
                existing = ProxmoxCredentials.query.first()
                if existing:
                    db.session.delete(existing)
                    db.session.commit()
                    print("[DEBUG] Existing credentials removed")
                response = jsonify({'message': 'Proxmox credentials removed'})
                response.headers['Content-Type'] = 'application/json'
                return response, 200

            print("\n[DEBUG] Saving Proxmox credentials...")
            print(f"[DEBUG] Request data: {json.dumps(data, indent=2)}")
            
            # Update or create credentials
            credentials = ProxmoxCredentials.query.first()
            is_new = False
            if not credentials:
                credentials = ProxmoxCredentials()
                db.session.add(credentials)
                is_new = True
                print("[DEBUG] Creating new ProxmoxCredentials record")
            else:
                print("[DEBUG] Updating existing ProxmoxCredentials record")

            print("[DEBUG] Processing form data:")
            print(f"[DEBUG] hostname: {data.get('hostname')}")
            print(f"[DEBUG] username: {data.get('username')}")
            print(f"[DEBUG] port: {data.get('port')}")
            print(f"[DEBUG] verify_ssl: {data.get('verify_ssl')}")

            credentials.hostname = data['hostname']
            credentials.username = data.get('username') if data.get('username') else None
            try:
                credentials.port = int(data.get('port', 8006))
            except (TypeError, ValueError):
                credentials.port = 8006
            credentials.verify_ssl = bool(data.get('verify_ssl', True))

            # Handle password authentication
            if 'password' in data and data['password']:
                print("[DEBUG] Setting up password authentication")
                credentials.password = data['password']
                print("[DEBUG] Password auth configured for user:", credentials.username)

            # Test connection if all required fields are present
            if credentials.hostname and credentials.username and credentials.password:
                try:
                    proxmox = credentials.get_proxmox_connection()
                    proxmox.nodes.get()
                except Exception as e:
                    print(f"[Settings] Connection test failed: {str(e)}")
                    response = jsonify({'warning': f'Saved credentials but connection test failed: {str(e)}'})
                    response.headers['Content-Type'] = 'application/json'
                    db.session.commit()
                    return response, 200

            db.session.commit()
            
            try:
                collect_metrics_job()
            except Exception as collection_error:
                print(f"[Metrics] Initial collection failed: {str(collection_error)}")
            
            response = jsonify({'message': 'Proxmox settings updated successfully'})
            response.headers['Content-Type'] = 'application/json'
            return response, 200
        except Exception as e:
            db.session.rollback()
            response = jsonify({'error': f'Failed to connect to Proxmox: {str(e)}'})
            response.headers['Content-Type'] = 'application/json'
            return response, 400
