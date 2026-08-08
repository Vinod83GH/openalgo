# Usage: .\deploy-to-lightsail.ps1 [mode]
#   mode: "full" (default) | "be" (backend only) | "fe" (frontend only)
#
# Examples:
#   .\deploy-to-lightsail.ps1 full   # Full rebuild (frontend + backend + restart)
#   .\deploy-to-lightsail.ps1 be     # Backend only (Docker rebuild, no frontend rebuild)
#   .\deploy-to-lightsail.ps1 fe     # Frontend only (rebuild frontend, copy dist into container)

param(
    [ValidateSet("full", "be", "fe")]
    [string]$Mode = "full"
)

$ErrorActionPreference = "Stop"

$INSTANCE_IP = "3.7.93.99"
$SSH_KEY = "ubuntu-keypair-prod.pem"
$GITHUB_REPO = "git@github.com:Vinod83GH/openalgo.git"
$BRANCH = "aug26-changes"
$APP_DIR = "/home/ubuntu/openalgo"

Write-Host "=== OpenAlgo Lightsail Deployment ===" -ForegroundColor Cyan
Write-Host "Mode     : $Mode"
Write-Host "Instance : $INSTANCE_IP"
Write-Host "Branch   : $BRANCH"
Write-Host ""

function Invoke-SSH {
    param([string]$Cmd)
    & ssh -i $SSH_KEY -o StrictHostKeyChecking=no ubuntu@$INSTANCE_IP $Cmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed: $Cmd" }
}

# ============================================================
# COMMON STEPS (all modes)
# ============================================================

# STEP 1 - Copy .env to instance
Write-Host "Step 1 - Copying .env to instance..." -ForegroundColor Yellow
& scp -i $SSH_KEY -o StrictHostKeyChecking=no .env ubuntu@${INSTANCE_IP}:/home/ubuntu/.env-openalgo
if ($LASTEXITCODE -ne 0) { throw "scp .env failed" }
Write-Host "  Done" -ForegroundColor Green

# STEP 2 - Sync code on instance
Write-Host ""
Write-Host "Step 2 - Syncing code on instance..." -ForegroundColor Yellow
$HTTPS_REPO = "https://github.com/Vinod83GH/openalgo.git"
Invoke-SSH "if [ -d '$APP_DIR/.git' ]; then cd $APP_DIR; git fetch origin; git checkout $BRANCH; git reset --hard origin/$BRANCH; else git clone --branch $BRANCH $HTTPS_REPO $APP_DIR; fi"
Write-Host "  Code synced to branch: $BRANCH" -ForegroundColor Green

# STEP 3 - Copy .env into app directory
Write-Host ""
Write-Host "Step 3 - Placing .env in app directory..." -ForegroundColor Yellow
Invoke-SSH "cp /home/ubuntu/.env-openalgo $APP_DIR/.env && chmod 600 $APP_DIR/.env"
Write-Host "  Done" -ForegroundColor Green

# STEP 4 - Set up persistent data directories + sync strategy modules
Write-Host ""
Write-Host "Step 4 - Setting up data directories & syncing modules..." -ForegroundColor Yellow
Invoke-SSH "sudo mkdir -p /mnt/openalgo-data/{db,log,log/strategies,strategies/scripts,strategies/state,strategies/examples,keys} && sudo touch /mnt/openalgo-data/strategies/strategy_configs.json && sudo chown -R 1000:1000 /mnt/openalgo-data && sudo chmod -R 755 /mnt/openalgo-data && sudo chmod 700 /mnt/openalgo-data/keys"
Invoke-SSH "cp $APP_DIR/strategies/positional_state_helper.py /mnt/openalgo-data/strategies/positional_state_helper.py 2>/dev/null; cp $APP_DIR/strategies/positional_entry_monitor.py /mnt/openalgo-data/strategies/positional_entry_monitor.py 2>/dev/null; cp $APP_DIR/strategies/positional_exit_monitor.py /mnt/openalgo-data/strategies/positional_exit_monitor.py 2>/dev/null; echo OK"
Write-Host "  Done" -ForegroundColor Green

# STEP 5 - Write production docker-compose.yaml
Write-Host ""
Write-Host "Step 5 - Writing production docker-compose.yaml..." -ForegroundColor Yellow
$composeContent = "services:`n  openalgo:`n    image: openalgo:latest`n    build:`n      context: .`n      dockerfile: Dockerfile`n    container_name: openalgo-app`n    network_mode: host`n    volumes:`n      - /mnt/openalgo-data/db:/app/db`n      - /mnt/openalgo-data/log:/app/log`n      - /mnt/openalgo-data/strategies:/app/strategies`n      - /mnt/openalgo-data/keys:/app/keys`n      - $APP_DIR/.env:/app/.env:ro`n    restart: unless-stopped`n    healthcheck:`n      test: [""CMD"", ""python3"", ""-c"", ""import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/ping')""]`n      interval: 30s`n      timeout: 10s`n      retries: 3`n      start_period: 60s"
$composeBytes = [System.Text.Encoding]::UTF8.GetBytes($composeContent)
$composeB64 = [Convert]::ToBase64String($composeBytes)
Invoke-SSH "echo $composeB64 | base64 -d > $APP_DIR/docker-compose.prod.yaml"
Write-Host "  Done" -ForegroundColor Green

# ============================================================
# MODE-SPECIFIC STEPS
# ============================================================

if ($Mode -eq "fe") {
    # FRONTEND ONLY — build frontend on instance, copy dist into running container
    Write-Host ""
    Write-Host "=== FRONTEND-ONLY DEPLOY ===" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "Step 6 - Building frontend on instance..." -ForegroundColor Yellow
    Invoke-SSH "cd $APP_DIR/frontend && npm install && NODE_OPTIONS=--max-old-space-size=1536 npm run build"
    Write-Host "  Frontend built" -ForegroundColor Green

    Write-Host ""
    Write-Host "Step 7 - Copying dist into running container..." -ForegroundColor Yellow
    Invoke-SSH "docker cp $APP_DIR/frontend/dist/. openalgo-app:/app/frontend/dist/"
    Write-Host "  Done — frontend updated (no restart needed)" -ForegroundColor Green

} elseif ($Mode -eq "be") {
    # BACKEND ONLY — Docker build (uses cached frontend layer if unchanged)
    Write-Host ""
    Write-Host "=== BACKEND-ONLY DEPLOY ===" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "Step 6 - Building Docker image (backend, cached frontend)..." -ForegroundColor Yellow
    Write-Host "  Tip: Monitor with: ssh -i $SSH_KEY ubuntu@$INSTANCE_IP 'tail -f /tmp/openalgo-build.log'" -ForegroundColor Gray
    Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml build 2>&1 | tee /tmp/openalgo-build.log"
    Write-Host "  Build complete" -ForegroundColor Green

    Write-Host ""
    Write-Host "Step 7 - Restarting application..." -ForegroundColor Yellow
    Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml down --remove-orphans 2>/dev/null || true"
    Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml up -d"
    Write-Host "  Started" -ForegroundColor Green

} else {
    # FULL — no-cache rebuild (frontend + backend from scratch)
    Write-Host ""
    Write-Host "=== FULL DEPLOY (frontend + backend) ===" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "Step 6 - Building Docker image (--no-cache, full rebuild)..." -ForegroundColor Yellow
    Write-Host "  Tip: Monitor with: ssh -i $SSH_KEY ubuntu@$INSTANCE_IP 'tail -f /tmp/openalgo-build.log'" -ForegroundColor Gray
    Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml build --no-cache 2>&1 | tee /tmp/openalgo-build.log"
    Write-Host "  Build complete" -ForegroundColor Green

    Write-Host ""
    Write-Host "Step 7 - Restarting application..." -ForegroundColor Yellow
    Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml down --remove-orphans 2>/dev/null || true"
    Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml up -d"
    Write-Host "  Started" -ForegroundColor Green

    # Systemd service (only on full deploy)
    Write-Host ""
    Write-Host "Step 8 - Registering systemd service..." -ForegroundColor Yellow
    $svcContent = "[Unit]`nDescription=OpenAlgo Docker Compose Stack`nRequires=docker.service`nAfter=docker.service network-online.target`nWants=network-online.target`n`n[Service]`nType=oneshot`nRemainAfterExit=yes`nWorkingDirectory=$APP_DIR`nExecStart=/usr/bin/docker compose -f docker-compose.prod.yaml up -d`nExecStop=/usr/bin/docker compose -f docker-compose.prod.yaml down`nTimeoutStartSec=300`n`n[Install]`nWantedBy=multi-user.target"
    $svcBytes = [System.Text.Encoding]::UTF8.GetBytes($svcContent)
    $svcB64 = [Convert]::ToBase64String($svcBytes)
    Invoke-SSH "echo $svcB64 | base64 -d | sudo tee /etc/systemd/system/openalgo.service > /dev/null"
    Invoke-SSH "sudo systemctl daemon-reload && sudo systemctl enable openalgo"
    Write-Host "  Done" -ForegroundColor Green
}

# ============================================================
# HEALTH CHECK (all modes except fe)
# ============================================================

if ($Mode -ne "fe") {
    Write-Host ""
    Write-Host "Waiting 60 seconds for app to become healthy..." -ForegroundColor Yellow
    Start-Sleep -Seconds 60

    Write-Host ""
    Write-Host "Container status:" -ForegroundColor Yellow
    Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml ps"

    Write-Host ""
    Write-Host "Last 20 log lines:" -ForegroundColor Yellow
    Invoke-SSH "cd $APP_DIR && docker compose -f docker-compose.prod.yaml logs openalgo --tail=20"
}

Write-Host ""
Write-Host "=== Deployment Complete ($Mode) ===" -ForegroundColor Green
Write-Host "  App: http://$INSTANCE_IP"
Write-Host ""
Write-Host "Usage: .\deploy-to-lightsail.ps1 [full|be|fe]" -ForegroundColor Cyan
