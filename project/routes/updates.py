from flask import jsonify, request, session
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

scheduler = BackgroundScheduler()
scheduler.start()
from datetime import datetime
from models import (
    UpdateSchedule, DashboardLog, NodeUpdateStatus, 
    ProxmoxCredentials, db
)
from utils.node_updater import check_all_nodes_updates, execute_update

def register_routes(app):
    @app.route('/api/updates/check', methods=['POST'])
    def check_updates():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            # Log that update check was initiated
            log_entry = DashboardLog(
                action="Manual update check initiated",
                status='info'
            )
            db.session.add(log_entry)
            db.session.commit()
            
            check_all_nodes_updates()
            return jsonify({'message': 'Update check initiated successfully'}), 200
        except Exception as e:
            # Log the error
            log_entry = DashboardLog(
                action=f"Update check failed: {str(e)}",
                status='error'
            )
            db.session.add(log_entry)
            db.session.commit()
            return jsonify({'error': f'Failed to check updates: {str(e)}'}), 500

    @app.route('/api/updates/schedule', methods=['POST'])
    def schedule_update():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        if not data or 'scheduled_time' not in data:
            return jsonify({'error': 'Missing scheduled time'}), 400
        
        try:
            scheduled_time = datetime.fromisoformat(data['scheduled_time'].replace('Z', '+00:00'))
            update = UpdateSchedule(
                node_name=data.get('node_name'),
                scheduled_time=scheduled_time
            )
            db.session.add(update)
            db.session.commit()
            
            scheduler.add_job(
                func=execute_update,
                trigger='date',
                run_date=scheduled_time,
                args=[update.id],
                id=f'update_{update.id}'
            )
            
            return jsonify({'message': 'Update scheduled successfully', 'id': update.id}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

    @app.route('/api/updates/status/<int:update_id>', methods=['GET'])
    def get_update_status(update_id):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        update = UpdateSchedule.query.get_or_404(update_id)
        return jsonify({
            'id': update.id,
            'node_name': update.node_name,
            'scheduled_time': update.scheduled_time.isoformat(),
            'status': update.status,
            'completed_at': update.completed_at.isoformat() if update.completed_at else None,
            'error_message': update.error_message
        })
