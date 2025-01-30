import logging
from flask import current_app
from models import (
    ProxmoxCredentials, HostMetrics, VMMetrics, 
    ContainerMetrics, ClusterMetrics, DashboardLog, db
)
from datetime import datetime

# Configure logger
logger = logging.getLogger(__name__)

def calculate_disk_usage(config, disk_info, is_vm=True):
    """Calculate disk usage for a VM or container
    
    Args:
        config: VM/container configuration dictionary
        disk_info: Current disk status information
        is_vm: True if calculating for VM, False for container
    
    Returns:
        tuple: (disk_total, disk_used, error_message)
    """
    disk_total = 0
    disk_used = 0
    error = None
    
    try:
        # Calculate total disk space
        if is_vm:
            disk_prefixes = ('scsi', 'virtio', 'ide', 'sata')
        else:
            disk_prefixes = ('mp', 'rootfs')
            
        for key, value in config.items():
            if any(key.startswith(prefix) for prefix in disk_prefixes):
                if 'size' in value:
                    size_str = value.split(',')[0].replace('size=', '')
                    if size_str.endswith('G'):
                        disk_total += float(size_str[:-1]) * 1024 * 1024 * 1024
                    elif size_str.endswith('M'):
                        disk_total += float(size_str[:-1]) * 1024 * 1024
        
        # Calculate used disk space
        if is_vm:
            if 'disk' in disk_info:
                disk_used = sum(dev.get('used', 0) for dev in disk_info['disk'].values())
        else:
            if 'disk' in disk_info:
                disk_used = disk_info['disk']
                
    except Exception as e:
        error = str(e)
        
    return disk_total, disk_used, error

def format_uptime(seconds):
    """Convert seconds to human readable uptime format"""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    
    return " ".join(parts)

def collect_metrics_job():
    """Background job to collect metrics from Proxmox"""
    print("\n[Metrics] Starting metrics collection...")
    
    credentials = ProxmoxCredentials.query.first()
    if not credentials:
        print("[Metrics] No Proxmox credentials configured")
        return
        
    print(f"[Metrics] Found credentials in database: hostname={credentials.hostname}, username={credentials.username}, verify_ssl={credentials.verify_ssl}, port={credentials.port}")

    try:
        print("[Metrics] Attempting to connect to Proxmox cluster...")
        proxmox = credentials.get_proxmox_connection()
        print("[Metrics] Successfully created Proxmox connection object")
        
        # Initialize cluster totals
        total_cores = 0
        total_memory = 0
        used_memory = 0
        total_disk = 0
        used_disk = 0
        
        nodes = proxmox.nodes.get()
        print(f"[Metrics] Found {len(nodes)} nodes in cluster")
        
        # Collect host metrics
        for node in nodes:
            node_name = node['node']
            status = proxmox.nodes(node_name).status.get()
            network = proxmox.nodes(node_name).network.get()
            
            # Find the primary IP address (usually from vmbr0)
            ip_address = None
            for iface in network:
                if iface.get('iface') == 'vmbr0' and 'address' in iface:
                    ip_address = iface['address'].split('/')[0]
                    break
            
            host_metrics = HostMetrics(
                node_name=node_name,
                ip_address=ip_address,
                cpu_usage=status['cpu'] * 100,
                cpu_cores=status['cpuinfo']['cpus'],
                memory_usage=(status['memory']['used'] / status['memory']['total']) * 100,
                memory_total=status['memory']['total'],
                disk_usage=(status['rootfs']['used'] / status['rootfs']['total']) * 100,
                uptime=status['uptime'],
                uptime_formatted=format_uptime(status['uptime'])
            )
            db.session.add(host_metrics)
            
            # Collect VM metrics
            failed_vms = []
            for vm in proxmox.nodes(node_name).qemu.get():
                try:
                    vm_status = proxmox.nodes(node_name).qemu(vm['vmid']).status.current.get()
                    if 'cpu' in vm_status:
                        # Calculate disk usage
                        vm_config = proxmox.nodes(node_name).qemu(vm['vmid']).config.get()
                        vm_disk_info = proxmox.nodes(node_name).qemu(vm['vmid']).status.current.get()
                        disk_total, disk_used, error = calculate_disk_usage(vm_config, vm_disk_info, is_vm=True)
                        
                        if error:
                            print(f"[Metrics] Failed to get disk info for VM {vm['vmid']}: {error}")
                            
                        vm_metrics = VMMetrics(
                            node_name=node_name,
                            vmid=vm['vmid'],
                            name=vm.get('name', ''),
                            status=vm['status'],
                            cpu_usage=vm_status.get('cpu', 0) * 100,
                            memory_usage=(vm_status['mem'] / vm_status['maxmem']) * 100 if 'mem' in vm_status and 'maxmem' in vm_status else 0,
                            disk_usage=(disk_used / disk_total * 100) if disk_total > 0 else 0
                        )
                        db.session.add(vm_metrics)
                except Exception as e:
                    print(f"[Metrics] Failed to collect metrics for VM {vm['vmid']}: {str(e)}")
                    failed_vms.append(vm['vmid'])
            
            # Collect container metrics
            failed_containers = []
            for ct in proxmox.nodes(node_name).lxc.get():
                try:
                    ct_status = proxmox.nodes(node_name).lxc(ct['vmid']).status.current.get()
                    if 'cpu' in ct_status:
                        # Calculate disk usage
                        ct_config = proxmox.nodes(node_name).lxc(ct['vmid']).config.get()
                        ct_disk_info = proxmox.nodes(node_name).lxc(ct['vmid']).status.current.get()
                        disk_total, disk_used, error = calculate_disk_usage(ct_config, ct_disk_info, is_vm=False)
                        
                        if error:
                            print(f"[Metrics] Failed to get disk info for Container {ct['vmid']}: {error}")
                            
                        ct_metrics = ContainerMetrics(
                            node_name=node_name,
                            container_id=ct['vmid'],
                            name=ct.get('name', ''),
                            status=ct['status'],
                            cpu_usage=ct_status.get('cpu', 0) * 100,
                            memory_usage=(ct_status['mem'] / ct_status['maxmem']) * 100 if 'mem' in ct_status and 'maxmem' in ct_status else 0,
                            disk_usage=(disk_used / disk_total * 100) if disk_total > 0 else 0
                        )
                        db.session.add(ct_metrics)
                except Exception as e:
                    print(f"[Metrics] Failed to collect metrics for Container {ct['vmid']}: {str(e)}")
                    failed_containers.append(ct['vmid'])
        
        # Create consolidated metrics log entry
        nodes = proxmox.nodes.get()
        total_vms = sum(len(proxmox.nodes(node['node']).qemu.get()) for node in nodes)
        total_containers = sum(len(proxmox.nodes(node['node']).lxc.get()) for node in nodes)
        
        # Create metrics log entry with failure details if any
        metrics_summary = f"Gathering metrics for - {len(nodes)} Hosts, {total_vms} VMs, {total_containers} Containers"
        try:
            log_entry = DashboardLog(
                action=metrics_summary,
                status='info' if not (failed_vms or failed_containers) else 'warning',
                created_at=datetime.utcnow(),
                details={"failed_vms": failed_vms, "failed_containers": failed_containers} if failed_vms or failed_containers else None
            )
            db.session.add(log_entry)
            db.session.flush()  # Get the ID without committing
            print(f"[Metrics] Created metrics log: id={log_entry.id}, action='{log_entry.action}', status='{log_entry.status}'")
        except Exception as e:
            print(f"[Metrics] Failed to create log entry: {str(e)}")

        # Update cluster totals from host metrics
        for node in proxmox.nodes.get():
            status = proxmox.nodes(node['node']).status.get()
            total_cores += status['cpuinfo']['cpus']
            total_memory += status['memory']['total']
            used_memory += status['memory']['used']
            total_disk += status['rootfs']['total']
            used_disk += status['rootfs']['used']

        # Save cluster metrics
        cluster_metrics = ClusterMetrics(
            total_cpu=total_cores,
            used_cpu=sum(node['cpu'] for node in proxmox.nodes.get()) * 100,
            total_memory=total_memory,
            used_memory=used_memory,
            total_disk=total_disk,
            used_disk=used_disk,
            node_count=len(nodes)
        )
        db.session.add(cluster_metrics)
        
        try:
            db.session.commit()
            print(f"[Metrics] Successfully collected metrics from {len(nodes)} nodes")
            print("[Metrics] Database commit successful")
        except Exception as e:
            print(f"[Metrics] Failed to commit to database: {str(e)}")
            db.session.rollback()
    
    except Exception as e:
        error_msg = f"Failed to collect metrics: {str(e)}"
        print(f"[Metrics] {error_msg}")
        try:
            log_entry = DashboardLog(
                action=error_msg,
                status='error',
                created_at=datetime.utcnow()
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as log_error:
            print(f"[Metrics] Failed to log error: {str(log_error)}")
            db.session.rollback()
