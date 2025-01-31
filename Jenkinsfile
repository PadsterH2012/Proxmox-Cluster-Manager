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

        stage('Run Tests') {
            steps {
                dir('project') {
                    sh """
                        docker compose -f docker-compose.test.yml up \
                            --abort-on-container-exit \
                            --exit-code-from web
                    """
                }
            }
            post {
                always {
                    junit 'project/test-results.xml'
                    sh 'docker compose -f project/docker-compose.test.yml down -v || true'
                }
            }
        }

        stage('Push to Docker Hub') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'docker-hub-credentials', usernameVariable: 'DOCKER_HUB_USERNAME', passwordVariable: 'DOCKER_HUB_PASSWORD')]) {
                    sh "echo $DOCKER_HUB_PASSWORD | docker login -u $DOCKER_HUB_USERNAME --password-stdin"
                    sh "docker push ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"
                    sh "docker push ${DOCKER_IMAGE_NAME}:latest"
                }
            }
        }

        stage('Deploy with Docker Compose') {
            steps {
                dir('project') {
                    sh 'docker compose --version'  // Check if docker-compose is installed.
                    sh 'docker compose up -d'
                }
            }
        }
    }

    post {
        always {
            dir('project') {
                sh 'docker compose down || true'  // Add || true to prevent failure if containers aren't running
            }
            sh 'docker logout'
        }
        failure {
            echo 'The Pipeline failed :('
        }
        success {
            echo 'The Pipeline completed successfully :)'
        }
    }
}
