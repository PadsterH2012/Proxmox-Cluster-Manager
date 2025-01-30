# Settings Page Description

The settings page provides a clean, organized interface for managing Proxmox Cluster Manager configurations through a tabbed layout that matches the dashboard's dark theme.

## Layout

### Header
- Page title "Cluster Settings"
- Connection status indicator showing current Proxmox connection state

### Tab Navigation
Three main tabs organize different settings categories:
1. Connection
2. Maintenance
3. Notifications

## Tab Contents

### Connection Tab
Primary configuration for Proxmox VE access:
- Proxmox Host input field
- Port number (default: 8006)
- Username/password authentication fields
- SSL verification toggle
- Save button with automatic connection testing

### Maintenance Tab
System maintenance configuration:
- Update check interval (hours)
- Metrics collection interval (minutes)
- Automatic VM migration toggle
- Save button for maintenance preferences

### Notifications Tab
Email notification preferences:
- Email notifications toggle
- Email address input
- Notification type checkboxes:
  - Updates Available
  - VM Migrations
  - System Errors
- Save button for notification settings

## Theme and Styling
- Dark theme matching dashboard
- Consistent color scheme:
  - Background: #1c1e21
  - Text: #fff / #e9ecef
  - Accent: #3498db
  - Form backgrounds: #2c2e33
- Responsive design adapting to different screen sizes
- Visual feedback for active tabs and form interactions

## Functionality
- Real-time connection status updates
- Form validation for required fields
- Automatic settings persistence
- Error handling with user feedback
- CSRF protection on all forms
