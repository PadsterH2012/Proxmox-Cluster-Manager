import os
import json
import time
from typing import List, Tuple, Dict, Optional
from proxmoxer import ProxmoxAPI
from models import db, DashboardLog, VMMetrics, ContainerMetrics, DrainedVM, ProxmoxCredentials

def get_node_vms(node_name: str) -> Tuple[List[int], List[int]]:
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

class NodeDrainer:
    def __init__(self):
        """Initialize the NodeDrainer"""
        self.proxmox = None
        self.has_credentials = False
        self._init_proxmox_connection()
        self.get_node_vms = get_node_vms  # Add reference to the function
    
    def _init_proxmox_connection(self):
        """Initialize Proxmox connection using stored credentials"""
        try:
            # Try to get credentials from database
            creds = ProxmoxCredentials.query.first()
            if creds and creds.hostname:
                if creds.username and creds.password:
                    self.proxmox = creds.get_proxmox_connection()
                    self.has_credentials = True
                else:
                    log = DashboardLog(
                        action="Proxmox credentials not configured - Please configure credentials in Settings > Proxmox Connection. You can use either username/password or API token authentication.",
                        status='warning'
                    )
                    db.session.add(log)
                    db.session.commit()
                    print("Warning: No valid Proxmox credentials configured")
            else:
                log = DashboardLog(
                    action="Proxmox connection not configured - Please configure your Proxmox server connection in Settings > Proxmox Connection.",
                    status='warning'
                )
                db.session.add(log)
                db.session.commit()
                print("Warning: No Proxmox connection configured")
        except Exception as e:
            print(f"Warning: Could not initialize Proxmox connection: {str(e)}")
        
    def get_available_nodes(self, exclude_node: str) -> List[str]:
        """Get list of available nodes excluding the one being drained"""
        nodes = []
        for node in self.proxmox.nodes.get():
            if node['node'] != exclude_node and node['status'] == 'online':
                nodes.append(node['node'])
        return nodes
        
    def get_node_resources(self, node_name: str) -> Dict:
        """Get resource usage for a node"""
        node = self.proxmox.nodes(node_name)
        status = node.status.get()
        return {
            'cpu': status['cpu'],
            'maxcpu': status['maxcpu'],
            'mem': status['memory']['used'],
            'maxmem': status['memory']['total']
        }
        
    def find_best_target_node(self, nodes: List[str], required_cpu: float, required_mem: int) -> Optional[str]:
        """Find the best node to migrate to based on resource availability"""
        best_node = None
        best_score = float('inf')
        
        for node in nodes:
            resources = self.get_node_resources(node)
            cpu_usage = resources['cpu'] / resources['maxcpu']
            mem_usage = resources['mem'] / resources['maxmem']
            
            # Calculate score (lower is better)
            score = cpu_usage + mem_usage
            
            # Check if node has enough resources
            if (resources['maxcpu'] - resources['cpu'] >= required_cpu and 
                resources['maxmem'] - resources['mem'] >= required_mem and 
                score < best_score):
                best_node = node
                best_score = score
                
        return best_node
        
    def can_migrate_vm(self, node_name: str, vmid: int) -> bool:
        """Check if a VM can be migrated (e.g., not using local storage)"""
        try:
            vm_config = self.proxmox.nodes(node_name).qemu(vmid).config.get()
            
            # Check if VM uses local storage
            for disk_key in vm_config:
                if disk_key.startswith('scsi') or disk_key.startswith('virtio') or disk_key.startswith('ide'):
                    if 'local' in vm_config[disk_key]:
                        return False
            return True
        except Exception as e:
            print(f"Error checking VM migration capability: {str(e)}")
            return False
            
    def migrate_vm(self, node_name: str, vmid: int, target_node: str) -> bool:
        """Migrate a VM to the target node"""
        try:
            # Start migration
            self.proxmox.nodes(node_name).qemu(vmid).migrate.post(
                target=target_node,
                online=1
            )
            
            # Wait for migration to complete
            while True:
                status = self.proxmox.nodes(node_name).qemu(vmid).status.current.get()
                if status.get('status') == 'stopped':
                    # Check if VM exists on target
                    try:
                        self.proxmox.nodes(target_node).qemu(vmid).status.current.get()
                        return True
                    except:
                        return False
                time.sleep(5)
                
        except Exception as e:
            print(f"Error migrating VM: {str(e)}")
            return False
            
    def migrate_container(self, node_name: str, ctid: int, target_node: str) -> bool:
        """Migrate a container to the target node"""
        try:
            # Start migration
            self.proxmox.nodes(node_name).lxc(ctid).migrate.post(
                target=target_node,
                restart=1
            )
            
            # Wait for migration to complete
            while True:
                try:
                    status = self.proxmox.nodes(node_name).lxc(ctid).status.current.get()
                except:
                    # Check if container exists on target
                    try:
                        self.proxmox.nodes(target_node).lxc(ctid).status.current.get()
                        return True
                    except:
                        return False
                time.sleep(5)
                
        except Exception as e:
            print(f"Error migrating container: {str(e)}")
            return False
            
    def drain_node(self, node_name: str) -> Tuple[List[int], List[int]]:
        """
        Drain all VMs and containers from a node
        Returns: Tuple of (failed_vms, failed_containers)
        """
        if not self.has_credentials:
            # Without credentials, we can only track VMs/containers in our database
            vms, containers = self.get_node_vms(node_name)
            log = DashboardLog(
                node_name=node_name,
                action=f"Cannot drain node - Proxmox credentials not configured",
                status='warning'
            )
            db.session.add(log)
            db.session.commit()
            return vms, containers

        failed_vms = []
        failed_containers = []
        
        # Get available target nodes
        target_nodes = self.get_available_nodes(node_name)
        if not target_nodes:
            raise Exception("No available target nodes found")
            
        # Get all VMs and containers
        vms = self.proxmox.nodes(node_name).qemu.get()
        containers = self.proxmox.nodes(node_name).lxc.get()
        
        # Migrate VMs
        for vm in vms:
            if vm['status'] == 'running':
                vmid = vm['vmid']
                if self.can_migrate_vm(node_name, vmid):
                    # Find best target node based on VM's resource usage
                    target_node = self.find_best_target_node(
                        target_nodes,
                        vm.get('cpu', 1),
                        vm.get('maxmem', 1024*1024*1024)
                    )
                    
                    if target_node and self.migrate_vm(node_name, vmid, target_node):
                        # Log successful migration
                        log = DashboardLog(
                            node_name=node_name,
                            action=f"Migrated VM {vmid} to {target_node}",
                            status='info'
                        )
                        db.session.add(log)
                    else:
                        failed_vms.append(vmid)
                else:
                    failed_vms.append(vmid)
                    
        # Migrate containers
        for ct in containers:
            if ct['status'] == 'running':
                ctid = ct['vmid']
                target_node = self.find_best_target_node(
                    target_nodes,
                    ct.get('cpu', 1),
                    ct.get('maxmem', 512*1024*1024)
                )
                
                if target_node and self.migrate_container(node_name, ctid, target_node):
                    # Log successful migration
                    log = DashboardLog(
                        node_name=node_name,
                        action=f"Migrated container {ctid} to {target_node}",
                        status='info'
                    )
                    db.session.add(log)
                else:
                    failed_containers.append(ctid)
                    
        db.session.commit()
        return failed_vms, failed_containers
        
    def shutdown_vms(self, node_name: str, vm_ids: List[int], container_ids: List[int]) -> bool:
        """Shutdown specific VMs and containers on a node"""
        if not self.has_credentials:
            # Without credentials, just track the VMs/containers that need shutdown
            for vmid in vm_ids:
                drained_vm = DrainedVM(
                    node_name=node_name,
                    vmid=vmid,
                    vm_type='qemu',
                    name=str(vmid),
                    status='pending_shutdown'
                )
                db.session.add(drained_vm)
                
            for ctid in container_ids:
                drained_vm = DrainedVM(
                    node_name=node_name,
                    vmid=ctid,
                    vm_type='lxc',
                    name=str(ctid),
                    status='pending_shutdown'
                )
                db.session.add(drained_vm)
                
            log = DashboardLog(
                node_name=node_name,
                action=f"Cannot shutdown VMs/containers - Proxmox credentials not configured",
                status='warning',
                details=json.dumps({
                    'vms': vm_ids,
                    'containers': container_ids
                })
            )
            db.session.add(log)
            db.session.commit()
            return True

        if not self.proxmox:
            raise Exception("Proxmox connection not initialized")
            
        try:
            # Get VM and container names before shutdown
            vm_names = {}
            container_names = {}
            
            for vmid in vm_ids:
                try:
                    config = self.proxmox.nodes(node_name).qemu(vmid).config.get()
                    vm_names[vmid] = config.get('name', str(vmid))
                except:
                    vm_names[vmid] = str(vmid)
                    
            for ctid in container_ids:
                try:
                    config = self.proxmox.nodes(node_name).lxc(ctid).config.get()
                    container_names[ctid] = config.get('hostname', str(ctid))
                except:
                    container_names[ctid] = str(ctid)
            
            # Shutdown and track VMs
            for vmid in vm_ids:
                self.proxmox.nodes(node_name).qemu(vmid).status.shutdown.post()
                drained_vm = DrainedVM(
                    node_name=node_name,
                    vmid=vmid,
                    vm_type='qemu',
                    name=vm_names[vmid]
                )
                db.session.add(drained_vm)
                
            # Shutdown and track containers
            for ctid in container_ids:
                self.proxmox.nodes(node_name).lxc(ctid).status.shutdown.post()
                drained_vm = DrainedVM(
                    node_name=node_name,
                    vmid=ctid,
                    vm_type='lxc',
                    name=container_names[ctid]
                )
                db.session.add(drained_vm)
                
            # Log the operation
            log = DashboardLog(
                node_name=node_name,
                action=f"Initiated shutdown of VMs {vm_ids} and containers {container_ids}",
                status='warning',
                details=json.dumps({
                    'vms': {str(vmid): name for vmid, name in vm_names.items()},
                    'containers': {str(ctid): name for ctid, name in container_names.items()}
                })
            )
            db.session.add(log)
            db.session.commit()
            
            return True
        except Exception as e:
            print(f"Error shutting down VMs/containers: {str(e)}")
            db.session.rollback()
            return False
