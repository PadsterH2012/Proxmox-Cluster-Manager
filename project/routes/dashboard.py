from flask import render_template, jsonify, session, redirect, request
from datetime import datetime, timedelta
import os
import json
from models import (
    HostMetrics, VMMetrics, ContainerMetrics, 
    ClusterMetrics, DashboardLog, NodeUpdateStatus, db
)
from utils.node_drainer import NodeDrainer

# Initialize NodeDrainer
node_drainer = NodeDrainer()

def verify_migration_completion(node_name, vm_id):
    """Verify if a VM/container has completed migration by checking config files"""
    try:
        # Check if config exists on other nodes
        for host in HostMetrics.query.with_entities(HostMetrics.node_name).distinct():
            if host.node_name != node_name:
                # This is a placeholder path - adjust based on actual Proxmox config location
                config_path = f"/etc/pve/nodes/{host.node_name}/qemu-server/{vm_id}.conf"
                if os.path.exists(config_path):
                    return True
        return False
    except Exception as e:
        print(f"Error verifying migration: {str(e)}")
        return False

def get_node_vms(node_name):
    """Get all VMs and containers running on a node"""
    vms = VMMetrics.query.filter_by(
        node_name=node_name,
        status='running'
    ).with_entities(VMMetrics.vmid).distinct().all()
    
    containers = ContainerMetrics.query.filter_by(
        node_name=node_name,
        status='running'
    ).with_entities(ContainerMetrics.container_id).distinct().all()
    
    return [vm.vmid for vm in vms], [ct.container_id for ct in containers]

def register_routes(app):
    # Drain node endpoint
    @app.route('/api/nodes/drain', methods=['POST'])
    def drain_node():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        if not data or 'node_name' not in data:
            return jsonify({'error': 'Missing node_name'}), 400
        
        node_name = data['node_name']
        
        try:
            # Start the drain process using NodeDrainer
            failed_vms, failed_containers = node_drainer.drain_node(node_name)
            
            # Log any failures
            if failed_vms or failed_containers:
                log = DashboardLog(
                    node_name=node_name,
                    action=f"Some VMs/containers could not be migrated",
                    status='warning',
                    details=json.dumps({
                        'failed_vms': failed_vms,
                        'failed_containers': failed_containers
                    })
                )
                db.session.add(log)
                db.session.commit()
            
            return jsonify({
                'message': 'Drain process completed',
                'failed_vms': failed_vms,
                'failed_containers': failed_containers
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # Shutdown VMs endpoint
    @app.route('/api/nodes/shutdown-vms', methods=['POST'])
    def shutdown_vms():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        if not data or 'node_name' not in data:
            return jsonify({'error': 'Missing node_name'}), 400
        
        node_name = data['node_name']
        
        try:
            # Get VMs and containers that need shutdown
            vms, containers = get_node_vms(node_name)
            
            # Use NodeDrainer to shutdown VMs and containers
            success = node_drainer.shutdown_vms(node_name, vms, containers)
            
            if not success:
                raise Exception("Failed to initiate shutdown of some VMs/containers")
            
            return jsonify({
                'message': 'Shutdown process started',
                'vms': len(vms),
                'containers': len(containers)
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # Migration status endpoint
    @app.route('/api/nodes/migration-status/<node_name>')
    def migration_status(node_name):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            # Get current VMs and containers on the node
            vms, containers = get_node_vms(node_name)
            
            # If no VMs/containers are running, migration is complete
            if not vms and not containers:
                return jsonify({
                    'status': 'completed',
                    'requires_shutdown': False
                })
            
            # Check if remaining VMs can be migrated
            requires_shutdown = False
            for vm_id in vms:
                if not node_drainer.can_migrate_vm(node_name, vm_id):
                    requires_shutdown = True
                    break
            
            return jsonify({
                'status': 'in_progress',
                'requires_shutdown': requires_shutdown,
                'remaining_vms': len(vms),
                'remaining_containers': len(containers)
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/')
    def index():
        if 'user_id' in session:
            return redirect('/dashboard')
        return render_template('index.html')

    @app.route('/dashboard')
    def dashboard():
        if 'user_id' not in session:
            return redirect('/')
        
        print("\n[DEBUG] ===== Dashboard Metrics =====")
        
        # Get cluster-wide metrics
        cluster_metrics = ClusterMetrics.query.order_by(ClusterMetrics.timestamp.desc()).first()
        print(f"[DEBUG] Cluster metrics found: {cluster_metrics is not None}")
        if cluster_metrics:
            print(f"[DEBUG] Cluster metrics timestamp: {cluster_metrics.timestamp}")
            print(f"[DEBUG] Total CPU: {cluster_metrics.total_cpu}")
            print(f"[DEBUG] Used CPU: {cluster_metrics.used_cpu}")
            print(f"[DEBUG] Total Memory: {cluster_metrics.total_memory}")
            print(f"[DEBUG] Used Memory: {cluster_metrics.used_memory}")
            print(f"[DEBUG] Node Count: {cluster_metrics.node_count}")
        
        # Get individual node metrics
        hosts_metrics = {}
        latest_host_metrics = db.session.query(
            HostMetrics.node_name,
            db.func.max(HostMetrics.timestamp).label('max_timestamp')
        ).group_by(HostMetrics.node_name).all()
        
        print(f"[DEBUG] Found {len(latest_host_metrics)} host metrics entries")
        for host_name, _ in latest_host_metrics:
            metric = HostMetrics.query.filter_by(node_name=host_name).order_by(HostMetrics.timestamp.desc()).first()
            print(f"[DEBUG] Host {host_name} metrics found: {metric is not None}")
            if metric:
                update_status = NodeUpdateStatus.query.filter_by(node_name=host_name).first()
                hosts_metrics[host_name] = {
                    'ip_address': metric.ip_address,
                    'cpu_usage': metric.cpu_usage,
                    'cpu_cores': metric.cpu_cores,
                    'memory_usage': metric.memory_usage,
                    'memory_total': metric.memory_total,
                    'disk_usage': metric.disk_usage,
                    'uptime': metric.uptime,
                    'uptime_formatted': metric.uptime_formatted,
                    'update_status': {
                        'updates_available': update_status.updates_available if update_status else 0,
                        'reboot_required': update_status.reboot_required if update_status else False,
                        'last_checked': update_status.last_checked if update_status else None
                    }
                }

        # Calculate cluster utilization percentages
        cpu_percent = (cluster_metrics.used_cpu / cluster_metrics.total_cpu) * 100 if cluster_metrics and cluster_metrics.total_cpu > 0 else 0
        memory_percent = (cluster_metrics.used_memory / cluster_metrics.total_memory) * 100 if cluster_metrics and cluster_metrics.total_memory > 0 else 0
        print(f"[DEBUG] CPU Usage: {cpu_percent:.1f}%")
        print(f"[DEBUG] Memory Usage: {memory_percent:.1f}%")

        vm_metrics = db.session.query(
            VMMetrics.vmid,
            db.func.max(VMMetrics.timestamp).label('max_timestamp')
        ).group_by(VMMetrics.vmid).all()
        
        print(f"[DEBUG] Found {len(vm_metrics)} VM metrics entries")
        total_vms = len(vm_metrics)
        online_vms = VMMetrics.query.filter(
            db.tuple_(VMMetrics.vmid, VMMetrics.timestamp).in_([
                (vm[0], vm[1]) for vm in vm_metrics
            ]),
            VMMetrics.status == 'running'
        ).count()

        container_metrics = db.session.query(
            ContainerMetrics.container_id,
            db.func.max(ContainerMetrics.timestamp).label('max_timestamp')
        ).group_by(ContainerMetrics.container_id).all()
        
        print(f"[DEBUG] Found {len(container_metrics)} container metrics entries")
        total_containers = len(container_metrics)
        online_containers = ContainerMetrics.query.filter(
            db.tuple_(ContainerMetrics.container_id, ContainerMetrics.timestamp).in_([
                (ct[0], ct[1]) for ct in container_metrics
            ]),
            ContainerMetrics.status == 'running'
        ).count()
        
        # Sort hosts by node name
        sorted_hosts = dict(sorted(hosts_metrics.items()))
        
        return render_template('dashboard.html',
                            hosts=sorted_hosts,
                            total_vms=total_vms,
                            online_vms=online_vms,
                            total_containers=total_containers,
                            online_containers=online_containers,
                            cpu_percent=cpu_percent,
                            memory_percent=memory_percent,
                            total_nodes=cluster_metrics.node_count if cluster_metrics else 0,
                            last_updated=cluster_metrics.timestamp if cluster_metrics else datetime.utcnow(),
                            total_cores=cluster_metrics.total_cpu if cluster_metrics else 0,
                            total_memory=cluster_metrics.total_memory if cluster_metrics else 0,
                            used_memory=cluster_metrics.used_memory if cluster_metrics else 0)

    @app.route('/api/metrics/hosts', methods=['GET'])
    def get_host_metrics():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        hosts = HostMetrics.query.order_by(HostMetrics.timestamp.desc()).limit(100).all()
        return jsonify([{
            'node_name': h.node_name,
            'cpu_usage': h.cpu_usage,
            'memory_usage': h.memory_usage,
            'disk_usage': h.disk_usage,
            'uptime': h.uptime,
            'timestamp': h.timestamp.isoformat()
        } for h in hosts])

    @app.route('/api/metrics/vms', methods=['GET'])
    def get_vm_metrics():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        vms = VMMetrics.query.order_by(VMMetrics.timestamp.desc()).limit(100).all()
        return jsonify([{
            'node_name': vm.node_name,
            'vmid': vm.vmid,
            'name': vm.name,
            'status': vm.status,
            'cpu_usage': vm.cpu_usage,
            'memory_usage': vm.memory_usage,
            'disk_usage': vm.disk_usage,
            'timestamp': vm.timestamp.isoformat()
        } for vm in vms])

    @app.route('/api/metrics/containers', methods=['GET'])
    def get_container_metrics():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        containers = ContainerMetrics.query.order_by(ContainerMetrics.timestamp.desc()).limit(100).all()
        return jsonify([{
            'node_name': c.node_name,
            'container_id': c.container_id,
            'name': c.name,
            'status': c.status,
            'cpu_usage': c.cpu_usage,
            'memory_usage': c.memory_usage,
            'disk_usage': c.disk_usage,
            'timestamp': c.timestamp.isoformat()
        } for c in containers])

    @app.route('/api/logs', methods=['GET'])
    def get_logs():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            # Get info and warning logs
            logs = DashboardLog.query.filter(
                DashboardLog.status.in_(['info', 'warning'])  # Get both info and warning logs
            ).order_by(DashboardLog.created_at.desc()).all()

            # Debug print
            print("\n[DEBUG] All logs from database:")
            for log in logs:
                print(f"[LOG] id={log.id}, action='{log.action}', status='{log.status}', created_at={log.created_at}")

            # Convert to JSON
            log_list = [{
                'id': log.id,
                'node_name': log.node_name,
                'action': log.action,
                'status': log.status,
                'created_at': log.created_at.isoformat(),
                'details': log.details
            } for log in logs]

            print("[DEBUG] Returning logs:", log_list)
            return jsonify(log_list)

        except Exception as e:
            print(f"[ERROR] Failed to fetch logs: {str(e)}")
            return jsonify({'error': 'Failed to fetch logs'}), 500

    @app.route('/api/metrics/collect', methods=['POST'])
    def trigger_metrics_collection():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            from utils.metrics_collector import collect_metrics_job
            collect_metrics_job()
            return jsonify({'message': 'Metrics collection triggered successfully'})
        except Exception as e:
            print(f"[ERROR] Failed to collect metrics: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/logs', methods=['POST'])
    def create_log():
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        if not data or 'action' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
        
        log = DashboardLog(
            node_name=data.get('node_name'),
            action=data['action'],
            status=data.get('status', 'info'),
            details=data.get('details')
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'id': log.id,
            'node_name': log.node_name,
            'action': log.action,
            'status': log.status,
            'created_at': log.created_at.isoformat(),
            'details': log.details
        }), 201
