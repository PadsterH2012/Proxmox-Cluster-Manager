# Project TODOs and Improvements

## Resource Management
- [ ] Implement Resource Manager:
  - [ ] Collect and store VM/container metrics (CPU load, CPU count, Memory Usage, Memory total)
  - [ ] Create resource optimization recommendations after 7-day analysis
  - [ ] Develop Resource Manager Dashboard for per VM/container stats
  - [ ] Add RM Auto Button for automatic resource adjustments
  - [x] Implement maintenance window scheduling in settings

## Balance Cluster
- [ ] Enhance cluster balancing system:
  - [ ] Implement VM/Container migration for optimal host utilization
  - [ ] Add threshold/equal distribution settings
  - [ ] Implement availability verification post-migration
  - [ ] Add frequency settings for automatic checks
  - [ ] Create RM Auto Button for automatic balancing
  - [ ] Set up Migration Logs card for tracking

## Migration Process
- [ ] Integrate migration system with:
  - [ ] Cluster Update rolling reboot process
  - [ ] Balance cluster operations

## Settings
- [x] Add backup and restore functionality for settings

## High Priority
- [ ] Fix Schedule Cluster Update button functionality
- [ ] Implement proper logging for:
  - Scheduled Cluster Update process
  - Migration operations
  - List of needed updates per node when updates are found

## UI Improvements
- [ ] Move JavaScript code to separate files
- [ ] Fix schedule update per node modal closing on refresh
- [ ] Fix schedule update per node modal icon not easily visible in dark theme, make icon lighter

## Cluster Management
- [ ] Enhance cluster balancing algorithm:
  - Consider current CPU/memory usage
  - Optimize VM allocation based on resource availability
  - Integrate and improve current_load_balencing_script.sh functionality

## Scheduled Updates
- [ ] Implement full cluster update workflow:
  - Schedule update time
  - Add "Run Now" button to Schedule Update modal for both individual nodes and cluster-wide updates
  - Add "Run Now" option in cluster update workflow for immediate execution
  - Migrate VMs/containers with proper logging
  - Handle migration failures gracefully
  - Perform apt upgrade and reboot
  - Restart any failed migrations after reboot
  - Continue process across all nodes

## Technical Debt
- [ ] Repurpose code from current_load_balencing_script.sh, and look to use within webapp
- [ ] Document cluster management processes

## Project Setup & Security
- [ ] Implement authentication check for all routes/pages
- [ ] Set up Git repository for version control
- [ ] Configure Jenkins pipeline for CI/CD
- [ ] Create comprehensive unit test suite
- [ ] Review and rename project folder structure
