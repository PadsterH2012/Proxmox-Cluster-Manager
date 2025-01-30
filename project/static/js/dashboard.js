// Get CSRF token for protected routes
function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
}

// Check connection status
function checkConnectionStatus() {
    // First check if we have a stored connection status
    const storedStatus = sessionStorage.getItem('connectionStatus');
    if (storedStatus) {
        const status = JSON.parse(storedStatus);
        updateConnectionStatusUI(status);
        
        // If we have a stored status, still verify it with the server
        // but show the stored status immediately for better UX
        verifyConnectionStatus();
        return;
    }

    // If no stored status, fetch fresh status
    fetchConnectionStatus();
}

function fetchConnectionStatus() {
    console.log('[Dashboard] Fetching connection status...');
    fetch('/api/connection-status')
        .then(response => {
            console.log('[Dashboard] Connection status response:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('[Dashboard] Connection status data:', data);
            updateConnectionStatusUI(data);
            // Store the status in sessionStorage
            sessionStorage.setItem('connectionStatus', JSON.stringify(data));
        })
        .catch(error => {
            console.error('Error checking connection status:', error);
        });
}

function verifyConnectionStatus() {
    fetch('/api/connection-status')
        .then(response => response.json())
        .then(data => {
            updateConnectionStatusUI(data);
            sessionStorage.setItem('connectionStatus', JSON.stringify(data));
        })
        .catch(console.error);
}

function updateConnectionStatusUI(data) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    
    if (data.connected) {
        statusDot.classList.add('connected');
        statusDot.classList.remove('disconnected');
        statusText.textContent = `Connected - ${data.auth_type}`;
    } else {
        statusDot.classList.add('disconnected');
        statusDot.classList.remove('connected');
        statusText.textContent = `Not Connected - ${data.auth_type}`;
    }
}

// Auto-refresh dashboard every 30 seconds
let autoRefreshInterval = setInterval(function() {
    console.log('[Dashboard] Auto-refreshing page...');
    window.location.reload();
}, 30000);

// Connection status check interval
let connectionCheckInterval;

// Function to trigger metrics collection
async function triggerMetricsCollection() {
    console.log('[Dashboard] Triggering metrics collection...');
    try {
        const response = await fetch('/api/metrics/collect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to collect metrics');
        }
        
        console.log('[Dashboard] Metrics collection triggered successfully');
        alert('Metrics collection triggered successfully');
        window.location.reload();
    } catch (error) {
        console.error('[Dashboard] Failed to collect metrics:', error);
        alert('Failed to collect metrics: ' + error.message);
    }
}

// Function to trigger update check
async function checkUpdates() {
    try {
        const response = await fetch('/api/updates/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to check updates');
        }
        
        // Refresh logs to show new update check entries
        loadLogs();
    } catch (error) {
        alert('Failed to check updates: ' + error.message);
    }
}

// Function to load logs from the database
async function loadLogs() {
    try {
        const response = await fetch('/api/logs', {
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        const logs = await response.json();
        
        // Update each log section
        const sections = ['migration-log', 'resource-log', 'updates-log', 'dashboard-log'];
        sections.forEach(sectionId => {
            const container = document.getElementById(sectionId);
            container.innerHTML = ''; // Clear existing logs
            
            // Filter logs based on section
            let sectionLogs = [];
            if (sectionId === 'migration-log') {
                sectionLogs = logs.filter(log => log.action.toLowerCase().includes('migrat'));
            } else if (sectionId === 'resource-log') {
                sectionLogs = logs.filter(log => log.action.toLowerCase().includes('resource'));
            } else if (sectionId === 'updates-log') {
                sectionLogs = logs.filter(log => {
                    const action = log.action.toLowerCase();
                    return action.includes('update') || 
                           action.includes('checking for updates') || 
                           action.includes('no updates found') || 
                           action.includes('updates found') || 
                           action.includes('requires reboot') ||
                           action.includes('package:');  // Include package update entries
                });
            } else if (sectionId === 'dashboard-log') {
                // Show metrics logs and errors
                sectionLogs = logs.filter(log => {
                    const action = log.action.toLowerCase();
                    return action.includes('gathering metrics') || 
                           action.includes('failed to collect metrics') ||
                           log.status === 'error';  // Include error logs
                });
            }

            // Get checkbox states from the log controls
            const controls = container.parentElement.querySelector('.log-controls');
            const checkboxes = controls.querySelectorAll('input[type="checkbox"]');
            const showInfo = checkboxes[0].checked;
            const showWarn = checkboxes[1].checked;
            const showCritical = checkboxes[2].checked;
            
            // Filter and display logs based on checkbox states
            const filteredLogs = sectionLogs.filter(log => {
                const status = (log.status || '').toLowerCase();
                if (status === 'info' && !showInfo) return false;
                if (status === 'warning' && !showWarn) return false;
                if (status === 'error' && !showCritical) return false;
                return true;
            });

            // Display the filtered logs
            filteredLogs.forEach(log => {
                const logEntry = document.createElement('div');
                logEntry.className = 'log-entry';
                logEntry.innerHTML = `
                    <span class="log-time">${new Date(log.created_at).toLocaleTimeString()}</span>
                    <span class="log-message ${log.status}">${log.action}</span>
                `;
                container.appendChild(logEntry);
            });
        });
    } catch (error) {
        console.error('Failed to load logs:', error);
    }
}

// Modal handling
let updateModal;
let updateForm;
let updateNodeName;
let isModalOpen = false;

// Track draining nodes and their status
const drainingNodes = new Map();

document.addEventListener('DOMContentLoaded', () => {
    console.log('[Dashboard] Initializing dashboard...');
    // Initialize connection status check
    checkConnectionStatus();
    connectionCheckInterval = setInterval(checkConnectionStatus, 30000);
    console.log('[Dashboard] Connection status check interval set');

    updateModal = document.getElementById('updateModal');
    updateForm = document.getElementById('updateForm');
    updateNodeName = document.getElementById('updateNodeName');

    // Add event listeners for drain buttons
    document.querySelectorAll('.drain-btn').forEach(button => {
        button.addEventListener('click', handleDrainClick);
    });

    // Add event listeners for shutdown indicators
    document.querySelectorAll('.shutdown-indicator').forEach(indicator => {
        indicator.addEventListener('click', handleShutdownClick);
    });

    // Show modal when schedule update button is clicked (not drain button)
    document.querySelectorAll('.btn[data-node]:not(.drain-btn)').forEach(button => {
        button.addEventListener('click', () => {
            const nodeName = button.getAttribute('data-node');
            updateNodeName.value = nodeName;
            openUpdateModal();
        });
    });

    // Handle form submission
    updateForm.addEventListener('submit', handleUpdateFormSubmit);

    // Close modal when clicking outside
    window.onclick = (event) => {
        if (event.target === updateModal) {
            closeUpdateModal();
        }
    };

    // Add event listeners to checkboxes to reload logs when changed
    document.querySelectorAll('.log-controls input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', loadLogs);
    });

    // Load logs initially and refresh every 5 seconds
    console.log('[Dashboard] Loading initial logs...');
    loadLogs();
    setInterval(() => {
        console.log('[Dashboard] Refreshing logs...');
        loadLogs();
    }, 5000);
});

function openUpdateModal() {
    isModalOpen = true;
    updateModal.style.display = 'block';
    
    // Set default time to current time + 5 minutes
    const now = new Date();
    now.setMinutes(now.getMinutes() + 5);
    
    // Format date to YYYY-MM-DDThh:mm
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    
    const defaultTime = `${year}-${month}-${day}T${hours}:${minutes}`;
    document.getElementById('updateTime').value = defaultTime;
    
    // Clear auto-refresh and connection check while modal is open
    clearInterval(autoRefreshInterval);
    clearInterval(connectionCheckInterval);
}

function closeUpdateModal() {
    isModalOpen = false;
    updateModal.style.display = 'none';
    // Restore auto-refresh and connection check when modal is closed
    autoRefreshInterval = setInterval(function() {
        window.location.reload();
    }, 30000);
    connectionCheckInterval = setInterval(checkConnectionStatus, 30000);
}

// Handle drain button click
async function handleDrainClick(e) {
    const button = e.target;
    const nodeName = button.getAttribute('data-node');
    const currentStatus = button.getAttribute('data-status');

    if (currentStatus === 'ready') {
        try {
            const response = await fetch('/api/nodes/drain', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                credentials: 'same-origin',
                body: JSON.stringify({ node_name: nodeName })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to start draining');
            }

            // Update button state
            button.setAttribute('data-status', 'draining');
            drainingNodes.set(nodeName, {
                status: 'draining',
                startTime: Date.now()
            });

            // Start checking migration status
            checkMigrationStatus(nodeName);
        } catch (error) {
            alert('Failed to start draining: ' + error.message);
        }
    }
}

// Handle shutdown indicator click
async function handleShutdownClick(e) {
    const indicator = e.target;
    const nodeName = indicator.getAttribute('data-node');

    if (confirm(`Are you sure you want to shutdown VMs/containers on ${nodeName}?`)) {
        try {
            const response = await fetch('/api/nodes/shutdown-vms', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                credentials: 'same-origin',
                body: JSON.stringify({ node_name: nodeName })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to shutdown VMs/containers');
            }

            // Hide the shutdown indicator
            indicator.style.display = 'none';
        } catch (error) {
            alert('Failed to shutdown VMs/containers: ' + error.message);
        }
    }
}

// Check migration status periodically
async function checkMigrationStatus(nodeName) {
    const nodeStatus = drainingNodes.get(nodeName);
    if (!nodeStatus || nodeStatus.status !== 'draining') return;

    try {
        const response = await fetch(`/api/nodes/migration-status/${nodeName}`, {
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        const data = await response.json();

        if (data.status === 'completed') {
            // Migration completed
            const button = document.querySelector(`.drain-btn[data-node="${nodeName}"]`);
            button.setAttribute('data-status', 'ready');
            drainingNodes.delete(nodeName);
        } else if (data.requires_shutdown) {
            // Show shutdown indicator
            const indicator = document.querySelector(`.shutdown-indicator[data-node="${nodeName}"]`);
            if (indicator) {
                indicator.style.display = 'inline-block';
            }
        } else {
            // Continue checking status
            setTimeout(() => checkMigrationStatus(nodeName), 5000);
        }
    } catch (error) {
        console.error('Failed to check migration status:', error);
        setTimeout(() => checkMigrationStatus(nodeName), 5000);
    }
}

async function handleUpdateFormSubmit(e) {
    e.preventDefault();
    const formData = {
        node_name: updateNodeName.value,
        scheduled_time: document.getElementById('updateTime').value
    };

    try {
        const response = await fetch('/api/updates/schedule', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify(formData)
        });

        const data = await response.json();
        if (response.ok) {
            alert('Update scheduled successfully');
            closeUpdateModal();
        } else {
            alert(`Failed to schedule update: ${data.error}`);
        }
    } catch (error) {
        alert('Failed to schedule update: ' + error.message);
    }
}
