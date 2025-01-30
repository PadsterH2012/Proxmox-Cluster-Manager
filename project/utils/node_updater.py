import paramiko
from datetime import datetime
from flask import current_app
from models import (
    DashboardLog, NodeUpdateStatus, HostMetrics, 
    ProxmoxCredentials, UpdateSchedule, db
)

def check_node_updates(node_name, ip_address):
    """Check for system updates on a node via SSH"""
    try:
        # Get Proxmox credentials
        credentials = ProxmoxCredentials.query.first()
        if not credentials:
            raise Exception('Proxmox credentials not configured')

        # Initialize SSH client
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Connect using Proxmox credentials (strip @pam from username)
        ssh_username = credentials.username.split('@')[0]
        ssh.connect(ip_address, username=ssh_username, password=credentials.password)
        
        # Log checking for updates
        log_entry = DashboardLog(
            node_name=node_name,
            action=f"{node_name} - checking for updates",
            status='info'
        )
        db.session.add(log_entry)
        db.session.commit()  # Commit immediately to ensure log is saved
        
        # Update package lists
        _, stdout, stderr = ssh.exec_command('apt update 2>&1')
        update_output = stdout.read().decode().strip()
        update_error = stderr.read().decode().strip()
        
        if "Error:" in update_output or "Error:" in update_error:
            raise Exception(f"Failed to update package lists: {update_output}\n{update_error}")
            
        # Log the apt update
        log_entry = DashboardLog(
            node_name=node_name,
            action=f"{node_name} - apt update completed",
            status='info'
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Get list of updates
        _, stdout, _ = ssh.exec_command('apt list --upgradable 2>/dev/null | grep -v "Listing..."')
        updates_list = stdout.read().decode().strip().split('\n')
        updates_count = len([u for u in updates_list if u.strip()])  # Count non-empty lines
        
        # Log each update if there are any
        if updates_count > 0:
            log_entry = DashboardLog(
                node_name=node_name,
                action=f"{node_name} - {updates_count} updates found:",
                status='warning'
            )
            db.session.add(log_entry)
            
            # Log each package update
            for update in updates_list:
                if update.strip():  # Skip empty lines
                    try:
                        # Parse package info (format: name/source [arch] version)
                        package_info = update.split('/')
                        package_name = package_info[0]
                        
                        # Handle kernel packages differently
                        if package_name.startswith('proxmox-kernel'):
                            version_info = package_info[1].split(' ')[0].strip()
                        else:
                            version_info = package_info[1].split(']')[-1].strip()
                        
                        log_entry = DashboardLog(
                            node_name=node_name,
                            action=f"{node_name} - Package: {package_name} -> {version_info}",
                            status='info'
                        )
                        db.session.add(log_entry)
                    except Exception as parse_error:
                        # If parsing fails, log the raw update line
                        log_entry = DashboardLog(
                            node_name=node_name,
                            action=f"{node_name} - Update: {update}",
                            status='info'
                        )
                        db.session.add(log_entry)
            
            db.session.commit()
        
        # Check if reboot is required
        _, stdout, _ = ssh.exec_command('test -f /var/run/reboot-required && echo "yes" || echo "no"')
        reboot_required = stdout.read().decode().strip() == "yes"
        
        ssh.close()
        
        # Log results based on conditions
        if updates_count == 0:
            log_entry = DashboardLog(
                node_name=node_name,
                action=f"{node_name} - no updates found",
                status='info'
            )
        else:
            log_entry = DashboardLog(
                node_name=node_name,
                action=f"{node_name} - {updates_count} updates found",
                status='warning'
            )
        db.session.add(log_entry)
        
        if reboot_required:
            log_entry = DashboardLog(
                node_name=node_name,
                action=f"{node_name} - requires reboot",
                status='warning'
            )
            db.session.add(log_entry)
        
        db.session.commit()
        return updates_count, reboot_required
    except Exception as e:
        error_msg = str(e)
        print(f"Failed to check updates for node {node_name}: {error_msg}")
        # Log the error
        log_entry = DashboardLog(
            node_name=node_name,
            action=f"Failed to check updates: {error_msg}",
            status='error'
        )
        db.session.add(log_entry)
        db.session.commit()
        return None, None

def check_all_nodes_updates():
    """Background job to check for updates on all nodes"""
    with current_app.app_context():
        print(f"\n[{datetime.now()}] Starting update check...")
        try:
            # Get all nodes from host metrics
            latest_host_metrics = db.session.query(
                HostMetrics.node_name,
                HostMetrics.ip_address,
                db.func.max(HostMetrics.timestamp)
            ).group_by(HostMetrics.node_name, HostMetrics.ip_address).all()
            
            for node_name, ip_address, _ in latest_host_metrics:
                # Get or create node update status
                update_status = NodeUpdateStatus.query.filter_by(node_name=node_name).first()
                if not update_status:
                    update_status = NodeUpdateStatus(node_name=node_name)
                    db.session.add(update_status)
                
                # Check for updates if we have an IP address
                if ip_address:
                    updates_count, reboot_required = check_node_updates(
                        node_name, 
                        ip_address
                    )
                    
                    if updates_count is not None:
                        update_status.updates_available = updates_count
                        update_status.reboot_required = reboot_required
                        update_status.last_checked = datetime.utcnow()
            
            db.session.commit()
            print("[Updates] Successfully checked updates for all nodes")
        
        except Exception as e:
            error_msg = str(e)
            print(f"[Updates] Failed to check updates: {error_msg}")
            # Log the error
            log_entry = DashboardLog(
                action=f"Update check failed: {error_msg}",
                status='error'
            )
            db.session.add(log_entry)
            db.session.commit()
            db.session.rollback()

def execute_update(update_id):
    """Execute a scheduled update"""
    with current_app.app_context():
        update = UpdateSchedule.query.get(update_id)
        if not update:
            return
        
        update.status = 'in_progress'
        db.session.commit()
        
        try:
            credentials = ProxmoxCredentials.query.first()
            if not credentials:
                raise Exception('Proxmox credentials not configured')
            
            proxmox = credentials.get_proxmox_connection()
            
            nodes_to_update = []
            if update.node_name:
                nodes = proxmox.nodes.get()
                if any(n['node'] == update.node_name for n in nodes):
                    nodes_to_update.append(update.node_name)
                else:
                    raise Exception(f"Node {update.node_name} not found")
            else:
                nodes_to_update = [n['node'] for n in proxmox.nodes.get()]
            
            for node_name in nodes_to_update:
                log_entry = DashboardLog(
                    node_name=node_name,
                    action=f"Starting update process for node {node_name}",
                    status='info'
                )
                db.session.add(log_entry)
                db.session.commit()
                
                # Get Proxmox credentials
                credentials = ProxmoxCredentials.query.first()
                if not credentials:
                    raise Exception('Proxmox credentials not configured')
                
                # Get node's IP address
                host_metric = HostMetrics.query.filter_by(node_name=node_name).order_by(HostMetrics.timestamp.desc()).first()
                if not host_metric or not host_metric.ip_address:
                    raise Exception(f"IP address not found for node {node_name}")
                
                # Initialize SSH client
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                try:
                    # Connect using Proxmox credentials (strip @pam from username)
                    ssh_username = credentials.username.split('@')[0]
                    ssh.connect(
                        host_metric.ip_address,
                        username=ssh_username,
                        password=credentials.password
                    )
                    
                    # Update package lists
                    _, stdout, stderr = ssh.exec_command('apt-get update')
                    if stderr.channel.recv_exit_status() != 0:
                        raise Exception(f"Failed to update package lists: {stderr.read().decode()}")
                    
                    # Perform upgrade
                    _, stdout, stderr = ssh.exec_command('DEBIAN_FRONTEND=noninteractive apt-get -y upgrade')
                    if stderr.channel.recv_exit_status() != 0:
                        raise Exception(f"Failed to upgrade packages: {stderr.read().decode()}")
                    
                    # Check if reboot is required
                    _, stdout, _ = ssh.exec_command('test -f /var/run/reboot-required && echo "yes" || echo "no"')
                    reboot_required = stdout.read().decode().strip() == "yes"
                    
                    if reboot_required:
                        log_entry = DashboardLog(
                            node_name=node_name,
                            action=f"Node {node_name} requires reboot after update",
                            status='warning'
                        )
                        db.session.add(log_entry)
                    
                    ssh.close()
                    
                except Exception as ssh_error:
                    raise Exception(f"SSH operation failed for node {node_name}: {str(ssh_error)}")
            
            update.status = 'completed'
            update.completed_at = datetime.utcnow()
            db.session.commit()
            
        except Exception as e:
            update.status = 'failed'
            update.error_message = str(e)
            update.completed_at = datetime.utcnow()
            db.session.commit()
