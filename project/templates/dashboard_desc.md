# Dashboard Description

The dashboard provides a comprehensive overview of the Proxmox cluster's status and metrics.

## Layout

### Metric Cards
At the top of the dashboard, four metric cards display key cluster statistics:
1. **VMs Card**: Shows the number of running VMs out of total VMs
2. **Containers Card**: Displays active LXC containers out of total containers
3. **Cluster CPU Card**: Shows overall CPU usage percentage and total core count
4. **Cluster Memory Card**: Displays memory usage percentage and total memory allocation

### Main Dashboard Sections
Below the metric cards, the dashboard is divided into four main sections:
1. **Cluster Metrics**: Shows detailed metrics with a button to trigger collection
2. **Updates**: Displays available updates with a check button
3. **Migration Status**: Shows the status of any ongoing migrations
4. **Resource Allocation**: Displays resource usage across the cluster

## Features

- Real-time connection status indicator
- Filterable log sections (Info, Warning, Critical)
- Update scheduling modal for node updates
- Responsive design that adapts to different screen sizes

## Functionality

- Metrics are automatically collected and displayed
- Users can manually trigger metrics collection
- Update checks can be performed on demand
- Migration status is monitored and displayed
- Resource allocation is tracked and visualized

## Technical Details

The dashboard interfaces with several backend APIs:
- `/api/metrics/hosts`: Retrieves host metrics
- `/api/metrics/vms`: Gets VM statistics
- `/api/metrics/containers`: Fetches container metrics
- `/api/metrics/collect`: Triggers metrics collection
- `/api/logs`: Manages system logs
