#!/usr/bin/env bash
# ==============================================================================
# TaskFlow Automated Production Deployment Script
# Targets: Ubuntu 22.04 / 24.04 LTS VM (AWS EC2, DigitalOcean Droplet, GCP)
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo " Starting TaskFlow Production Stack Deployment"
echo "=========================================================="

APP_DIR="/opt/taskflow"
REPO_URL="https://github.com/shivambhardwaj719/task_flow.git"
BRANCH="main"

# Step 1: Ensure system packages and Docker are installed
echo "[1/5] Checking Docker & Docker Compose installation..."
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing Docker Engine..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo systemctl enable --now docker
    echo "Docker installed successfully."
fi

# Step 2: Clone or update repository in /opt/taskflow
echo "[2/5] Synchronizing repository code in ${APP_DIR}..."
if [ ! -d "${APP_DIR}" ]; then
    sudo git clone -b "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
    sudo chown -R "$USER:$USER" "${APP_DIR}"
else
    cd "${APP_DIR}"
    git fetch origin "${BRANCH}"
    git reset --hard "origin/${BRANCH}"
fi

cd "${APP_DIR}"

# Step 3: Generate production .env configuration if not present
echo "[3/5] Verifying environment configuration..."
if [ ! -f ".env" ]; then
    echo "Generating new production .env file with cryptographic secrets..."
    RANDOM_SECRET=$(openssl rand -hex 32)
    cat <<EOF > .env
ENVIRONMENT=production
DEBUG=False
PROJECT_NAME=TaskFlow
VERSION=1.0.0
SECRET_KEY=${RANDOM_SECRET}
DATABASE_URL=postgresql://taskflow:taskflow_password@db:5432/taskflow_db
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
CACHE_DEFAULT_TTL=300
OVERDUE_TASK_CHECK_INTERVAL_SECONDS=60
EOF
    echo ".env created with randomized SECRET_KEY."
fi

# Step 4: Build and launch full Docker Compose stack
echo "[4/5] Building and launching containers via Docker Compose..."
docker compose pull || true
docker compose up -d --build --remove-orphans

# Step 5: Perform health check verification
echo "[5/5] Awaiting service health verification..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        echo ""
        echo "=========================================================="
        echo " TaskFlow deployed successfully!"
        echo " Health Check: http://localhost:8000/health"
        echo " OpenAPI Docs: http://localhost:8000/docs"
        echo " Prometheus:   http://localhost:8000/metrics"
        echo "=========================================================="
        exit 0
    fi
    echo -n "."
    sleep 2
done

echo ""
echo "WARNING: Stack launched, but healthcheck did not report healthy within 60s."
echo "Inspect logs using: docker compose logs -f"
exit 1
