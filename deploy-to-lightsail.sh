#!/bin/bash
set -e

INSTANCE_IP="3.109.183.169"
SSH_KEY="ubuntu-keypair-prod.pem"
HTTPS_REPO="https://github.com/Vinod83GH/openalgo.git"
BRANCH="Kill-switch"
APP_DIR="/home/ubuntu/openalgo"

echo "=== OpenAlgo Lightsail Deployment (Build-on-Instance) ==="
echo "Instance : $INSTANCE_IP"
echo "Repo     : $HTTPS_REPO"
echo "Branch   : $BRANCH"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Copy .env to instance
# ─────────────────────────────────────────────────────────────────────────────
echo "Step 1 - Copying .env to instance..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no .env ubuntu@$INSTANCE_IP:/home/ubuntu/.env-openalgo

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Ensure Docker + git are installed
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Step 2 - Checking Docker and git..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "docker --version && docker compose version"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "sudo apt-get install -y -qq git"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Clone or pull latest code on instance
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Step 3 - Syncing code on instance (branch: $BRANCH)..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "
if [ -d '$APP_DIR/.git' ]; then
  echo 'Repo exists — pulling latest...'
  cd $APP_DIR
  git fetch origin
  git checkout $BRANCH
  git reset --hard origin/$BRANCH
else
  echo 'Cloning repo...'
  git clone --branch $BRANCH $HTTPS_REPO $APP_DIR
fi
"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Place .env and set up data directories
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Step 4 - Placing .env and setting up data directories..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "cp /home/ubuntu/.env-openalgo $APP_DIR/.env && chmod 600 $APP_DIR/.env"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "sudo mkdir -p /mnt/openalgo-data/{db,log,log/strategies,strategies/scripts,strategies/examples,keys} && sudo chown -R 1000:1000 /mnt/openalgo-data && sudo chmod -R 755 /mnt/openalgo-data && sudo chmod 700 /mnt/openalgo-data/keys"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Write production docker-compose.yaml
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Step 5 - Writing production docker-compose.yaml..."
cat > /tmp/docker-compose.prod.yaml << COMPOSE
services:
  openalgo:
    image: openalgo:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: openalgo-app
    network_mode: host
    volumes:
      - /mnt/openalgo-data/db:/app/db
      - /mnt/openalgo-data/log:/app/log
      - /mnt/openalgo-data/strategies:/app/strategies
      - /mnt/openalgo-data/keys:/app/keys
      - ${APP_DIR}/.env:/app/.env:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/ping')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
COMPOSE
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no /tmp/docker-compose.prod.yaml ubuntu@$INSTANCE_IP:$APP_DIR/docker-compose.prod.yaml

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Build Docker image on instance
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Step 6 - Building Docker image on instance (~10-15 min)..."
echo "  Monitor: ssh -i $SSH_KEY ubuntu@$INSTANCE_IP 'tail -f /tmp/openalgo-build.log'"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "cd $APP_DIR && docker compose -f docker-compose.prod.yaml build --no-cache 2>&1 | tee /tmp/openalgo-build.log"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Restart containers
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Step 7 - Restarting application..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "cd $APP_DIR && docker compose -f docker-compose.prod.yaml down --remove-orphans 2>/dev/null || true"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "cd $APP_DIR && docker compose -f docker-compose.prod.yaml up -d"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Systemd service
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Step 8 - Registering systemd service..."
cat > /tmp/openalgo.service << SVC
[Unit]
Description=OpenAlgo Docker Compose Stack
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yaml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yaml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
SVC
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no /tmp/openalgo.service ubuntu@$INSTANCE_IP:/home/ubuntu/openalgo.service
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP "sudo mv /home/ubuntu/openalgo.service /etc/systemd/system/openalgo.service && sudo systemctl daemon-reload && sudo systemctl enable openalgo"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 9 — Health check
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Waiting 75 seconds for app to become healthy..."
sleep 75

echo ""
echo "Step 9 - Container status..."
ssh -i "$SSH_KEY" ubuntu@$INSTANCE_IP "cd $APP_DIR && docker compose -f docker-compose.prod.yaml ps"

echo ""
echo "Step 9 - Last 30 log lines..."
ssh -i "$SSH_KEY" ubuntu@$INSTANCE_IP "cd $APP_DIR && docker compose -f docker-compose.prod.yaml logs openalgo --tail=30"

echo ""
echo "Step 9 - Health endpoint..."
curl -f "http://$INSTANCE_IP/api/v1/ping" && echo " ✓ Health check passed" || echo " ✗ Health check failed"

echo ""
echo "=== Deployment Complete ==="
echo "  App: http://$INSTANCE_IP"
echo ""
echo "For future updates, just run this script again — it will git pull and rebuild."
