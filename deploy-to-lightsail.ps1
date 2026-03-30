$ErrorActionPreference = "Stop"

$INSTANCE_IP = "3.109.183.169"
$SSH_KEY = "ubuntu-keypair-prod.pem"
$GITHUB_REPO = "git@github.com:Vinod83GH/openalgo.git"
$BRANCH = "Kill-switch"
$APP_DIR = "/home/ubuntu/openalgo"

Write-Host "=== OpenAlgo Lightsail Deployment (Build-on-Instance) ===" -ForegroundColor Cyan
Write-Host "Instance : $INSTANCE_IP"
Write-Host "Repo     : $GITHUB_REPO"
Write-Host "Branch   : $BRANCH"
Write-Host ""

function Invoke-SSH {
    param([string]$Cmd)
    & ssh -i $SSH_KEY -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP $Cmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed: $Cmd" }
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Copy .env to instance
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "Step 1 - Copying .env to instance..." -ForegroundColor Yellow
& scp -i $SSH_KEY -o StrictHostKeyChecking=no .env ubuntu@${INSTANCE_IP}:/home/ubuntu/.env-openalgo
if ($LASTEXITCODE -ne 0) { throw "scp .env failed" }
Write-Host "  Done" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Ensure Docker is installed
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 2 - Checking Docker installation..." -ForegroundColor Yellow
Invoke-SSH "docker --version && docker compose version"
Write-Host "  Docker OK" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Ensure Git is installed and SSH key is set up for GitHub
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 3 - Ensuring git is installed..." -ForegroundColor Yellow
Invoke-SSH "sudo apt-get install -y -qq git"
Write-Host "  Git OK" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Clone or pull latest code on instance
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 4 - Syncing code on instance..." -ForegroundColor Yellow

# Use HTTPS clone (no SSH key needed on instance)
$HTTPS_REPO = "https://github.com/Vinod83GH/openalgo.git"

Invoke-SSH @"
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
"@
Write-Host "  Code synced to branch: $BRANCH" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Copy .env into app directory
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 5 - Placing .env in app directory..." -ForegroundColor Yellow
Invoke-SSH "cp /home/ubuntu/.env-openalgo $APP_DIR/.env && chmod 600 $APP_DIR/.env"
Write-Host "  Done" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Set up persistent data directories
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 6 - Setting up data directories..." -ForegroundColor Yellow
Invoke-SSH "sudo mkdir -p /mnt/openalgo-data/{db,log,log/strategies,strategies/scripts,strategies/examples,keys} && sudo chown -R 1000:1000 /mnt/openalgo-data && sudo chmod -R 755 /mnt/openalgo-data && sudo chmod 700 /mnt/openalgo-data/keys"
Write-Host "  Done" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Write production docker-compose.yaml (uses local build, host volumes)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 7 - Writing production docker-compose.yaml..." -ForegroundColor Yellow

$composeLines = @(
    "services:",
    "  openalgo:",
    "    image: openalgo:latest",
    "    build:",
    "      context: .",
    "      dockerfile: Dockerfile",
    "    container_name: openalgo-app",
    "    network_mode: host",
    "    volumes:",
    "      - /mnt/openalgo-data/db:/app/db",
    "      - /mnt/openalgo-data/log:/app/log",
    "      - /mnt/openalgo-data/strategies:/app/strategies",
    "      - /mnt/openalgo-data/keys:/app/keys",
    "      - $APP_DIR/.env:/app/.env:ro",
    "    restart: unless-stopped",
    "    healthcheck:",
    "      test: [""CMD"", ""python3"", ""-c"", ""import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/ping')""]",
    "      interval: 30s",
    "      timeout: 10s",
    "      retries: 3",
    "      start_period: 60s"
)
$composeContent = $composeLines -join "`n"
$composeBytes = [System.Text.Encoding]::UTF8.GetBytes($composeContent)
$composeB64 = [Convert]::ToBase64String($composeBytes)
Invoke-SSH "echo $composeB64 | base64 -d > $APP_DIR/docker-compose.prod.yaml"
Write-Host "  Done" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Build Docker image on instance (this is the key step)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 8 - Building Docker image on instance (this takes ~10-15 min)..." -ForegroundColor Yellow
Write-Host "  Tip: You can monitor progress with:" -ForegroundColor Gray
Write-Host "  ssh -i $SSH_KEY ubuntu@$INSTANCE_IP 'tail -f /tmp/openalgo-build.log'" -ForegroundColor Gray
Write-Host ""

Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml build --no-cache 2>&1 | tee /tmp/openalgo-build.log; echo BUILD_EXIT_CODE:`$?"
Write-Host "  Build complete" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 9 — Stop old container and start new one
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 9 - Restarting application..." -ForegroundColor Yellow
Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml down --remove-orphans 2>/dev/null || true"
Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml up -d"
Write-Host "  Started" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 10 — Systemd service (auto-start on reboot)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Step 10 - Registering systemd service..." -ForegroundColor Yellow
$svcLines = @(
    "[Unit]",
    "Description=OpenAlgo Docker Compose Stack",
    "Requires=docker.service",
    "After=docker.service network-online.target",
    "Wants=network-online.target",
    "",
    "[Service]",
    "Type=oneshot",
    "RemainAfterExit=yes",
    "WorkingDirectory=$APP_DIR",
    "ExecStart=/usr/bin/docker compose -f docker-compose.prod.yaml up -d",
    "ExecStop=/usr/bin/docker compose -f docker-compose.prod.yaml down",
    "TimeoutStartSec=300",
    "",
    "[Install]",
    "WantedBy=multi-user.target"
)
$svcContent = $svcLines -join "`n"
$svcBytes = [System.Text.Encoding]::UTF8.GetBytes($svcContent)
$svcB64 = [Convert]::ToBase64String($svcBytes)
Invoke-SSH "echo $svcB64 | base64 -d | sudo tee /etc/systemd/system/openalgo.service > /dev/null"
Invoke-SSH "sudo systemctl daemon-reload && sudo systemctl enable openalgo"
Write-Host "  Done" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────────────────────
# STEP 11 — Health check
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Waiting 75 seconds for app to become healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 75

Write-Host ""
Write-Host "Step 11 - Container status..." -ForegroundColor Yellow
Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml ps"

Write-Host ""
Write-Host "Step 11 - Last 30 log lines..." -ForegroundColor Yellow
Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml logs openalgo --tail=30"

Write-Host ""
Write-Host "Step 11 - Health endpoint..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://$INSTANCE_IP/api/v1/ping" -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -eq 200) {
        Write-Host "  Health check PASSED (HTTP 200)" -ForegroundColor Green
    }
} catch {
    Write-Host "  Health check FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Debug: ssh -i $SSH_KEY ubuntu@$INSTANCE_IP 'docker logs openalgo-app --tail=50'"
}

Write-Host ""
Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host "  App: http://$INSTANCE_IP"
Write-Host ""
Write-Host "For future updates, just run this script again — it will git pull and rebuild." -ForegroundColor Cyan
