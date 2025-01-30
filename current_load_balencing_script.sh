#!/bin/bash

# Enable strict error handling
set -u
IFS=$'\n\t'

# Basic variables that need to be available immediately
LOGFILE="/var/log/proxmox_balancer.log"
LOCKFILE="/var/run/proxmox_balancer.lock"

# Configuration variables with defaults
declare -A CONFIG=(
    [LOAD_THRESHOLD]=70         # Load percentage threshold to trigger migration
    [CHECK_INTERVAL]=300        # Time between checks in seconds (5 minutes)
    [TIMEOUT]=1800             # Maximum time for a single migration in seconds (30 minutes)
    [MIN_LOAD_DIFF]=10         # Minimum load difference to trigger migration
    [BALANCE_MODE]="threshold"  # Options: "threshold" or "equal"
    [MAX_CONCURRENT_MIGRATIONS]=2  # Maximum number of concurrent migrations
    [CONFIG_FILE]="/etc/proxmox-balancer.conf"  # Configuration file path
    [LOCKFILE]="$LOCKFILE"
    [LOGFILE]="$LOGFILE"
    [DEBUG]=0                   # Debug mode flag
)

# Load configuration from file
load_config() {
    if [[ -f "${CONFIG[CONFIG_FILE]}" ]]; then
        while IFS='=' read -r key value; do
            # Skip comments and empty lines
            [[ "$key" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$key" ]] && continue
            
            # Trim whitespace
            key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            
            # Update configuration
            CONFIG[$key]="$value"
        done < "${CONFIG[CONFIG_FILE]}"
    fi
}

# Function to log messages
log_message() {
    local message="$1"
    local severity="${2:-info}"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $message" >> "$LOGFILE"
    echo "$message"
    pvesh create /nodes/$(hostname)/tasks/log \
        --msg "Load Balancer: $message" \
        --priority "$severity" \
        --user "root@pam" \
        2>/dev/null || true  # Added || true to prevent failure
}

# Enhanced dependency checking with version requirements
check_dependencies() {
    local -A required_versions=(
        ["jq"]="1.5"
        ["bc"]="1.0"
        ["pvesh"]="6.0"
    )
    
    local missing_deps=()
    for cmd in "${!required_versions[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing_deps+=("$cmd")
            continue
        fi
        
        # Version check for supported commands
        case "$cmd" in
            jq)
                local version
                version=$(jq --version 2>&1 | grep -oP '\d+\.\d+')
                if ! verify_version "$version" "${required_versions[$cmd]}"; then
                    log_message "Warning: $cmd version $version is below required ${required_versions[$cmd]}" "WARNING"
                fi
                ;;
        esac
    done
    
    if [[ ${#missing_deps[@]} -ne 0 ]]; then
        log_message "Error: Missing required dependencies: ${missing_deps[*]}" "ERROR"
        log_message "Please install missing dependencies:" "ERROR"
        log_message "apt-get update && apt-get install -y ${missing_deps[*]}" "ERROR"
        exit 1
    fi
}

# Version comparison function
verify_version() {
    local version=$1
    local required=$2
    
    if [[ $(echo "$version >= $required" | bc -l) -eq 1 ]]; then
        return 0
    fi
    return 1
}

# Enhanced lock management with timeout
check_lock() {
    local timeout=10  # Lock timeout in seconds
    local start_time
    start_time=$(date +%s)
    
    while [[ -f "${CONFIG[LOCKFILE]}" ]]; do
        local pid
        pid=$(cat "${CONFIG[LOCKFILE]}" 2>/dev/null || echo "")
        
        # Check if PID is still running
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            if [[ $(($(date +%s) - start_time)) -gt $timeout ]]; then
                log_message "Lock timeout after $timeout seconds" "ERROR"
                exit 1
            fi
            sleep 1
            continue
        else
            # Stale lock file
            rm -f "${CONFIG[LOCKFILE]}"
            break
        fi
    done
    
    echo $$ > "${CONFIG[LOCKFILE]}"
}

# Enhanced metrics collection with averaging
get_node_metrics() {
    local node="$1"
    local samples=3
    local interval=2
    local cpu_total=0
    local mem_total=0
    
    for ((i=0; i<samples; i++)); do
        local stats
        stats=$(pvesh get /nodes/"$node"/status --output-format=json)
        
        # Get CPU and memory usage
        local cpu_usage
        cpu_usage=$(echo "$stats" | jq -r '.cpu * 100' | awk '{printf "%.0f", $1}')
        cpu_total=$((cpu_total + cpu_usage))
        
        local mem_used
        mem_used=$(echo "$stats" | jq -r '.memory.used')
        local mem_max
        mem_max=$(echo "$stats" | jq -r '.memory.total')
        local mem_usage
        mem_usage=$(echo "scale=2; $mem_used / $mem_max * 100" | bc | awk '{printf "%.0f", $1}')
        mem_total=$((mem_total + mem_usage))
        
        [[ $i -lt $((samples-1)) ]] && sleep "$interval"
    done
    
    local avg_cpu=$((cpu_total / samples))
    local avg_mem=$((mem_total / samples))
    
    echo "$avg_cpu:$avg_mem"
}

# Function to balance cluster
balance_cluster() {
    log_message "Starting balance cluster check" "DEBUG"

    # Add error context
    if ! pvesh get /nodes --output-format=json > /dev/null 2>&1; then
        log_message "Unable to access Proxmox API - check permissions" "ERROR"
        return 1
    fi

    local max_iterations=5  # Maximum number of migrations per balance check
    local iteration=0
    local performed_migration=1
    
    while [[ $iteration -lt $max_iterations ]] && [[ $performed_migration -eq 1 ]]; do
        performed_migration=0
        iteration=$((iteration + 1))
        log_message "Starting iteration $iteration of $max_iterations" "DEBUG"
        
        # Get list of nodes
        log_message "Fetching node list" "DEBUG"
        local nodes_json
        nodes_json=$(pvesh get /nodes --output-format=json) || {
            log_message "Failed to get nodes list" "ERROR"
            return 1
        }

        # Parse nodes into array
        local nodes=()
        while IFS= read -r node; do
            [[ -n "$node" ]] && nodes+=("$node")
        done < <(echo "$nodes_json" | jq -r '.[].node')
        
        if [[ ${#nodes[@]} -eq 0 ]]; then
            log_message "No nodes found in cluster" "ERROR"
            return 1
        fi
        
        log_message "Found ${#nodes[@]} nodes in cluster" "DEBUG"
        
        declare -A node_loads
        declare -A node_metrics
        
        # Get metrics for each node
        for node in "${nodes[@]}"; do
            log_message "Getting metrics for node $node" "DEBUG"
            node_metrics[$node]=$(get_node_metrics "$node") || {
                log_message "Failed to get metrics for node $node" "ERROR"
                continue
            }
            
            local cpu_usage
            local mem_usage
            
            # Parse metrics with error checking
            if ! cpu_usage=$(echo "${node_metrics[$node]}" | cut -d: -f1); then
                log_message "Failed to parse CPU usage for node $node" "ERROR"
                continue
            fi
            if ! mem_usage=$(echo "${node_metrics[$node]}" | cut -d: -f2); then
                log_message "Failed to parse memory usage for node $node" "ERROR"
                continue
            fi
            
            # Use the higher of CPU or memory usage
            if [[ $cpu_usage -gt $mem_usage ]]; then
                node_loads[$node]=$cpu_usage
            else
                node_loads[$node]=$mem_usage
            fi
            
            log_message "Node $node - CPU: ${cpu_usage}%, Memory: ${mem_usage}%" "INFO"
        done
        
        # Check if we have enough valid nodes
        if [[ ${#node_loads[@]} -lt 2 ]]; then
            log_message "Not enough nodes with valid metrics for balancing" "ERROR"
            return 1
        fi
        
        # Find most and least loaded nodes
        local max_load=0
        local min_load=100
        local source_node=""
        local target_node=""
        
        for node in "${nodes[@]}"; do
            # Skip nodes with no valid metrics
            [[ -z "${node_loads[$node]}" ]] && continue
            
            local load=${node_loads[$node]}
            if [[ $load -gt $max_load ]]; then
                max_load=$load
                source_node=$node
            fi
            if [[ $load -lt $min_load ]]; then
                min_load=$load
                target_node=$node
            fi
        done
        
        # Verify we found valid source and target nodes
        if [[ -z "$source_node" ]] || [[ -z "$target_node" ]]; then
            log_message "Could not determine source and target nodes" "ERROR"
            return 1
        fi
        
        # Calculate load difference
        local load_diff=$((max_load - min_load))
        log_message "Load difference between nodes: $load_diff%" "DEBUG"
        
        # Check if migration is needed
        local should_migrate=0
        if [[ "${CONFIG[BALANCE_MODE]}" = "equal" ]]; then
            if [[ $load_diff -gt ${CONFIG[MIN_LOAD_DIFF]} ]]; then
                should_migrate=1
                log_message "Equal balance mode: Load difference ($load_diff%) exceeds threshold" "INFO"
            fi
        else
            if [[ $max_load -gt ${CONFIG[LOAD_THRESHOLD]} ]] && [[ $load_diff -gt ${CONFIG[MIN_LOAD_DIFF]} ]]; then
                should_migrate=1
                log_message "Threshold mode: Load ($max_load%) and difference ($load_diff%) exceed thresholds" "INFO"
            fi
        fi
        
        if [[ $should_migrate -eq 1 ]]; then
            log_message "Getting guest list for node $source_node" "DEBUG"
            # Get list of VMs on source node
            local qemu_ids
            qemu_ids=$(pvesh get /nodes/"$source_node"/qemu --output-format=json 2>/dev/null | jq -r '.[].vmid' 2>/dev/null || echo "")
            local lxc_ids
            lxc_ids=$(pvesh get /nodes/"$source_node"/lxc --output-format=json 2>/dev/null | jq -r '.[].vmid' 2>/dev/null || echo "")
            
            if [[ -z "$qemu_ids" ]] && [[ -z "$lxc_ids" ]]; then
                log_message "No guests found on source node $source_node" "WARNING"
                continue
            fi
            
            log_message "Found VMs: [$qemu_ids] and Containers: [$lxc_ids] on $source_node" "DEBUG"
            
            for vmid in $qemu_ids $lxc_ids; do
                [[ -z "$vmid" ]] && continue
                log_message "Attempting to migrate guest $vmid" "DEBUG"
                if migrate_guest "$vmid" "$source_node" "$target_node"; then
                    performed_migration=1
                    log_message "Rechecking cluster balance after migration..." "INFO"
                    sleep 30  # Wait for metrics to stabilize
                    break
                fi
            done
            
            if [[ $performed_migration -eq 0 ]]; then
                log_message "No suitable guests found for migration" "WARNING"
            fi
        else
            log_message "No migration needed. Max load: $max_load%, Min load: $min_load%" "INFO"
            break
        fi
    done
    
    if [[ $iteration -eq $max_iterations ]]; then
        log_message "Reached maximum number of migrations ($max_iterations) in this balance check" "WARNING"
    fi
    
    log_message "Balance cluster check completed" "DEBUG"
    return 0
}

# Function to migrate guest
migrate_guest() {
    local vmid="$1"
    local source="$2"
    local target="$3"
    local guest_type=""
    local initial_state=""
    
    # Get guest type and initial state
    if pvesh get /nodes/"$source"/qemu/"$vmid"/status/current --output-format=json >/dev/null 2>&1; then
        guest_type="qemu"
        initial_state=$(pvesh get /nodes/"$source"/qemu/"$vmid"/status/current --output-format=json | jq -r '.status')
    elif pvesh get /nodes/"$source"/lxc/"$vmid"/status/current --output-format=json >/dev/null 2>&1; then
        guest_type="lxc"
        initial_state=$(pvesh get /nodes/"$source"/lxc/"$vmid"/status/current --output-format=json | jq -r '.status')
    else
        log_message "Could not determine guest type for $vmid" "error"
        return 1
    fi
    
    # Skip if not running
    if [[ "$initial_state" != "running" ]]; then
        log_message "Skipping $vmid as it is not running (state: $initial_state)" "info"
        return 1
    fi
    
    log_message "Starting migration of guest $vmid from $source to $target" "info"
    
    # Start migration
    local start_time=$(date +%s)
    
    # Initiate migration
    pvesh create /nodes/"$source"/"$guest_type"/"$vmid"/migrate \
        --target "$target" --online 1 &>/dev/null &
    local migration_pid=$!
    
    # Monitor migration progress
    local migration_completed=0
    while kill -0 $migration_pid 2>/dev/null; do
        # Check for timeout
        if [[ $(($(date +%s) - start_time)) -gt ${CONFIG[TIMEOUT]} ]]; then
            kill $migration_pid 2>/dev/null
            log_message "Migration of guest $vmid timed out after ${CONFIG[TIMEOUT]} seconds" "error"
            return 1
        fi
        
        # Check if guest exists on target
        if pvesh get /nodes/"$target"/"$guest_type"/"$vmid"/status/current --output-format=json >/dev/null 2>&1; then
            local target_state
            target_state=$(pvesh get /nodes/"$target"/"$guest_type"/"$vmid"/status/current --output-format=json | jq -r '.status')
            log_message "Migration in progress - Guest $vmid state on target: $target_state" "info"
            
            # Check if guest no longer exists on source
            if ! pvesh get /nodes/"$source"/"$guest_type"/"$vmid"/status/current --output-format=json >/dev/null 2>&1; then
                if [[ "$target_state" = "$initial_state" ]]; then
                    migration_completed=1
                    break
                fi
            fi
        fi
        
        sleep 10
    done
    
    # Wait for migration process to complete
    wait $migration_pid
    local migration_status=$?
    
    # Verify final state
    if [[ $migration_status -eq 0 ]] && [[ $migration_completed -eq 1 ]]; then
        # Double check guest state on target
        if pvesh get /nodes/"$target"/"$guest_type"/"$vmid"/status/current --output-format=json >/dev/null 2>&1; then
            local final_state
            final_state=$(pvesh get /nodes/"$target"/"$guest_type"/"$vmid"/status/current --output-format=json | jq -r '.status')
            
            if [[ "$final_state" = "$initial_state" ]]; then
                log_message "Successfully migrated guest $vmid to $target and verified state" "info"
                return 0
            else
                log_message "Migration completed but guest $vmid is in wrong state (expected: $initial_state, got: $final_state)" "error"
                return 1
            fi
        else
            log_message "Migration failed - guest $vmid not found on target" "error"
            return 1
        fi
    else
        log_message "Migration failed for guest $vmid (status: $migration_status)" "error"
        return 1
    fi
}

# Function to check local resources
check_local_resources() {
    local node="$1"
    local vmid="$2"
    local guest_type="$3"
    local config
    
    if [[ "$guest_type" = "qemu" ]]; then
        config=$(pvesh get /nodes/"$node"/qemu/"$vmid"/config --output-format=json 2>/dev/null)
    else
        config=$(pvesh get /nodes/"$node"/lxc/"$vmid"/config --output-format=json 2>/dev/null)
    fi
    
    if [[ -z "$config" ]]; then
        log_message "Failed to get config for guest $vmid" "ERROR"
        return 1
    fi
    
    local storage_used=0
    
    # Check storage for QEMU VMs
    if [[ "$guest_type" = "qemu" ]]; then
        local disks
        disks=$(echo "$config" | jq -r 'to_entries | .[] | select(.key | match("^(scsi|ide|sata|virtio)\\d+$")) | .value')
        
        while IFS= read -r disk; do
            [[ -z "$disk" ]] && continue
            local storage
            storage=$(echo "$disk" | cut -d',' -f1 | cut -d':' -f1)
            local storage_type
            storage_type=$(pvesh get /storage/"$storage" --output-format=json 2>/dev/null | jq -r '.type')
            
            case $storage_type in
                dir|lvm|lvmthin|zfspool)
                    storage_used=1
                    log_message "Guest $vmid uses local storage: $storage ($storage_type)" "DEBUG"
                    break
                    ;;
            esac
        done <<< "$disks"
    fi
    
    # Check storage for LXC containers
    if [[ "$guest_type" = "lxc" ]]; then
        local rootfs
        rootfs=$(echo "$config" | jq -r '.rootfs')
        local storage
        storage=$(echo "$rootfs" | cut -d':' -f1)
        local storage_type
        storage_type=$(pvesh get /storage/"$storage" --output-format=json 2>/dev/null | jq -r '.type')
        
        case $storage_type in
            dir|lvm|lvmthin|zfspool)
                storage_used=1
                log_message "Guest $vmid uses local storage: $storage ($storage_type)" "DEBUG"
                ;;
        esac
    fi
    
    # Return 0 if migration is possible (no local storage used)
    # Return 1 if migration is not possible (local storage is used)
    return $storage_used
}

# Function to verify guest state
verify_guest_state() {
    local vmid="$1"
    local target="$2"
    local expected_state="$3"
    local max_attempts=12
    local attempt=0
    local check_interval=5
    local total_wait=$((max_attempts * check_interval))
    
    log_message "Verifying guest $vmid state on target $target (expected: $expected_state)" "DEBUG"
    
    while [[ $attempt -lt $max_attempts ]]; do
        local current_state=""
        
        # Try to get guest status for both QEMU and LXC
        if pvesh get /nodes/"$target"/qemu/"$vmid"/status/current --output-format=json >/dev/null 2>&1; then
            current_state=$(pvesh get /nodes/"$target"/qemu/"$vmid"/status/current --output-format=json | jq -r '.status')
        elif pvesh get /nodes/"$target"/lxc/"$vmid"/status/current --output-format=json >/dev/null 2>&1; then
            current_state=$(pvesh get /nodes/"$target"/lxc/"$vmid"/status/current --output-format=json | jq -r '.status')
        else
            log_message "Could not get status for guest $vmid on $target (attempt $((attempt + 1)))" "WARNING"
            sleep $check_interval
            attempt=$((attempt + 1))
            continue
        fi
        
        if [[ "$current_state" = "$expected_state" ]]; then
            log_message "Guest $vmid successfully verified in $expected_state state" "DEBUG"
            return 0
        fi
        
        log_message "Guest $vmid state is $current_state, waiting for $expected_state (attempt $((attempt + 1)))" "DEBUG"
        sleep $check_interval
        attempt=$((attempt + 1))
    done
    
    log_message "Failed to verify guest $vmid state after $total_wait seconds" "ERROR"
    return 1
}

# Main loop
main() {
    check_dependencies || {
        log_message "Dependency check failed" "error"
        exit 1
    }
    
    check_lock || {
        log_message "Lock check failed" "error"
        exit 1
    }

    log_message "Starting Proxmox Load Balancer" "info"
    log_message "Initial configuration: Mode=${CONFIG[BALANCE_MODE]}, Diff=${CONFIG[MIN_LOAD_DIFF]}" "info"
    
    while true; do
        log_message "Starting cluster balance check" "info"
        if ! balance_cluster; then
            log_message "Balance check failed" "error"
        fi
        log_message "Sleeping for ${CONFIG[CHECK_INTERVAL]} seconds" "info"
        sleep "${CONFIG[CHECK_INTERVAL]}"
    done
}

# Improved cleanup handling
cleanup() {
    local exit_code=$?
    log_message "Cleanup triggered with exit code: $exit_code" "info"
    rm -f "${CONFIG[LOCKFILE]}"
    log_message "Cleanup completed" "info"
    exit $exit_code
}

# Improve signal handling
trap 'log_message "Received EXIT signal" "info"; cleanup' EXIT
trap 'log_message "Received INT signal" "info"; exit 130' INT
trap 'log_message "Received TERM signal" "info"; exit 143' TERM

# Parse command line arguments with validation
parse_args() {
    while getopts "m:t:i:d:c:Dh" opt; do
        case $opt in
            m)
                if [[ "$OPTARG" =~ ^(threshold|equal)$ ]]; then
                    CONFIG[BALANCE_MODE]="$OPTARG"
                else
                    log_message "Invalid balance mode: $OPTARG" "ERROR"
                    exit 1
                fi
                ;;
            t)
                if [[ "$OPTARG" =~ ^[0-9]+$ ]] && [[ "$OPTARG" -ge 0 ]] && [[ "$OPTARG" -le 100 ]]; then
                    CONFIG[LOAD_THRESHOLD]="$OPTARG"
                else
                    log_message "Invalid threshold: $OPTARG" "ERROR"
                    exit 1
                fi
                ;;
            i)
                if [[ "$OPTARG" =~ ^[0-9]+$ ]] && [[ "$OPTARG" -ge 60 ]]; then
                    CONFIG[CHECK_INTERVAL]="$OPTARG"
                else
                    log_message "Invalid interval: $OPTARG" "ERROR"
                    exit 1
                fi
                ;;
            d)
                if [[ "$OPTARG" =~ ^[0-9]+$ ]] && [[ "$OPTARG" -ge 0 ]] && [[ "$OPTARG" -le 100 ]]; then
                    CONFIG[MIN_LOAD_DIFF]="$OPTARG"
                else
                    log_message "Invalid minimum difference: $OPTARG" "ERROR"
                    exit 1
                fi
                ;;
            c)
                CONFIG[CONFIG_FILE]="$OPTARG"
                ;;
            D)
                CONFIG[DEBUG]=1
                ;;
            h|?)
                echo "Usage: $0 [-m <mode>] [-t <threshold>] [-i <interval>] [-d <min_diff>] [-c <config>] [-D]"
                echo "Options:"
                echo "  -m <mode>       Balance mode: 'threshold' or 'equal' (default: ${CONFIG[BALANCE_MODE]})"
                echo "  -t <threshold>  Load threshold percentage (default: ${CONFIG[LOAD_THRESHOLD]})"
                echo "  -i <interval>   Check interval in seconds (default: ${CONFIG[CHECK_INTERVAL]})"
                echo "  -d <min_diff>   Minimum load difference to trigger migration (default: ${CONFIG[MIN_LOAD_DIFF]})"
                echo "  -c <config>     Configuration file path (default: ${CONFIG[CONFIG_FILE]})"
                echo "  -D              Enable debug mode"
                exit 1
                ;;
        esac
    done
}

# Start the script
parse_args "$@"