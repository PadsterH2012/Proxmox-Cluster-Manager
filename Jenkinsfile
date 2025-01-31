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
                dir('backend') {
                    sh 'ls -la'  // List all files in the backend directory for debugging
                    sh "docker build -t ${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG} ."
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
                sh 'docker compose --version'  // Check if docker-compose is installed.
                sh 'docker compose up -d'
            }
        }

        stage('Run Tests') {
            steps {
                script {
                    // Wait for the application to start
                    sh 'sleep 30'

                    // Basic health check
                    sh 'curl -f http://localhost:5000/ || exit 1'

                    // Add more comprehensive tests here
                    // sh 'docker-compose exec backend pytest'
                }
            }
        }
    }

    post {
        always {
            sh 'docker-compose down'
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