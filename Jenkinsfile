pipeline {
    agent any

    environment {
        DOCKER_HUB_CREDENTIALS = credentials('docker-hub-credentials')
        DOCKER_IMAGE_NAME = 'padster2012/proxmox-cluster-manager'
        DOCKER_IMAGE_TAG = "${env.BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                dir('project') {
                    sh 'ls -la'  // List all files in the project directory for debugging
                    sh """
                        docker build -t ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG} .
                        docker tag ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG} ${DOCKER_IMAGE_NAME}:latest
                    """
                }
            }
        }

        stage('Run Auth Tests') {
            steps {
                dir('project') {
                    sh """
                        docker compose -f docker-compose.test-1-auth.yml up \
                            --abort-on-container-exit \
                            --exit-code-from web
                    """
                }
            }
            post {
                always {
                    junit 'project/test-results-auth.xml'
                    // Only stop the web container, keep db running
                    sh 'docker compose -f project/docker-compose.test-1-auth.yml rm -f -s web || true'
                }
            }
        }

        stage('Run Settings Tests') {
            steps {
                dir('project') {
                    sh """
                        docker compose -f docker-compose.test-2-settings.yml up \
                            --abort-on-container-exit \
                            --exit-code-from web
                    """
                }
            }
            post {
                always {
                    junit 'project/test-results-settings.xml'
                    // Stop all containers after settings tests
                    sh '''
                        docker compose -f project/docker-compose.test-1-auth.yml down -v || true
                        docker compose -f project/docker-compose.test-2-settings.yml down -v || true
                    '''
                }
            }
        }

        /* Commenting out API tests for now
        stage('Run API Integration Tests') {
            steps {
                dir('project') {
                    sh """
                        docker compose -f docker-compose.test-3-api.yml up \
                            --abort-on-container-exit \
                            --exit-code-from web
                    """
                }
            }
            post {
                always {
                    junit 'project/test-results-api.xml'
                    // Stop all containers after API tests are done
                    sh '''
                        docker compose -f project/docker-compose.test-1-auth.yml down -v || true
                        docker compose -f project/docker-compose.test-2-settings.yml down -v || true
                        docker compose -f project/docker-compose.test-3-api.yml down -v || true
                    '''
                }
            }
        }
        */

        stage('Push to Docker Hub') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'docker-hub-credentials', usernameVariable: 'DOCKER_HUB_USERNAME', passwordVariable: 'DOCKER_HUB_PASSWORD')]) {
                    sh "echo $DOCKER_HUB_PASSWORD | docker login -u $DOCKER_HUB_USERNAME --password-stdin"
                    sh "docker push ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"
                    sh "docker push ${DOCKER_IMAGE_NAME}:latest"
                }
            }
        }

        stage('Deploy to Local Server') {
            when {
                expression {
                    // Only run deployment if credentials are available
                    try {
                        withCredentials([usernamePassword(credentialsId: 'proxman-deploy-credentials', usernameVariable: 'DEPLOY_USER', passwordVariable: 'DEPLOY_PASS')]) {
                            return true
                        }
                    } catch (e) {
                        echo "Skipping deployment: proxman-deploy-credentials not configured"
                        return false
                    }
                }
            }
            steps {
                script {
                    withCredentials([usernamePassword(credentialsId: 'proxman-deploy-credentials', usernameVariable: 'DEPLOY_USER', passwordVariable: 'DEPLOY_PASS')]) {
                        // Create a temporary docker-compose file with environment variables
                        sh '''
                            cat > deploy-compose.yml << 'EOL'
version: '3'
services:
  web:
    image: ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
    restart: unless-stopped
EOL
                        '''
                        
                        // Install sshpass if not already installed
                        sh 'which sshpass || apt-get update && apt-get install -y sshpass'
                        
                        // Deploy using credentials
                        sh """
                            sshpass -p "\${DEPLOY_PASS}" ssh -o StrictHostKeyChecking=no \${DEPLOY_USER}@localhost '
                                mkdir -p ~/proxmox-cluster-manager
                            '
                            
                            sshpass -p "\${DEPLOY_PASS}" scp -o StrictHostKeyChecking=no deploy-compose.yml \${DEPLOY_USER}@localhost:~/proxmox-cluster-manager/docker-compose.yml
                            
                            sshpass -p "\${DEPLOY_PASS}" ssh -o StrictHostKeyChecking=no \${DEPLOY_USER}@localhost '
                                cd ~/proxmox-cluster-manager && \
                                docker compose pull && \
                                docker compose down --remove-orphans && \
                                docker compose up -d
                            '
                            
                            rm deploy-compose.yml
                            
                            echo "Deployment completed successfully"
                        """
                    }
                }
            }
        }
    }

    post {
        always {
            dir('project') {
                sh 'docker compose down || true'  // Add || true to prevent failure if containers aren't running
            }
            sh 'docker logout || true'
        }
        failure {
            echo 'The Pipeline failed :('
        }
        success {
            echo 'The Pipeline completed successfully :)'
        }
    }
}
