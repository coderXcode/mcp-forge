# MCP Forge - Claude Desktop Plugin Installer (Windows)
# Usage: .\scripts\install_claude_plugin.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  MCP Forge - Claude Desktop Plugin Installer" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Docker
Write-Host "[1/5] Checking Docker..." -ForegroundColor Yellow
$running = docker inspect --format "{{.State.Running}}" mcp_forge_app 2>&1
if ($running -ne "true") {
    Write-Host "  ERROR: mcp_forge_app is not running. Run 'docker compose up -d' first." -ForegroundColor Red
    exit 1
}
Write-Host "  Docker OK -- mcp_forge_app is running." -ForegroundColor Green

# Step 2: Get token
Write-Host "[2/5] Fetching auth token from container..." -ForegroundColor Yellow
$token = (Get-Content .env | Where-Object { $_ -match '^MCP_AUTH_TOKEN=' } | Select-Object -First 1) -replace '^MCP_AUTH_TOKEN=',''
if (-not $token) {
    Write-Host "  ERROR: Could not read MCP_AUTH_TOKEN from .env" -ForegroundColor Red
    exit 1
}
Write-Host "  Token fetched OK." -ForegroundColor Green

# Locate system Python (used only to create the venv)
$sysPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $sysPython) { $sysPython = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $sysPython) {
    Write-Host "  ERROR: Python not found. Install Python 3.10+ and retry." -ForegroundColor Red
    exit 1
}
$projectPath = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
$venvDir     = Join-Path $projectPath ".venv"
$venvPython  = Join-Path $venvDir "Scripts\python.exe"
$requirementsFile = Join-Path $projectPath "requirements.txt"

# Step 3: Create venv + install dependencies
Write-Host "[3/5] Setting up Python virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path $venvPython)) {
    Write-Host "  Creating .venv..." -ForegroundColor Cyan
    & $sysPython -m venv $venvDir
}
Write-Host "  Installing dependencies into .venv (may take a minute)..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r $requirementsFile --quiet
Write-Host "  Virtual environment ready." -ForegroundColor Green

# Normalise to forward slashes for JSON
$pythonExe  = $venvPython  -replace "\\","/"
$projectPath = $projectPath -replace "\\","/"

# Step 4: Write config
Write-Host "[4/5] Writing Claude Desktop config..." -ForegroundColor Yellow

# Detect correct config path — handles both regular install and Windows Store (sandboxed) install
$configDir = $null

# Check Windows Store sandbox path first (Claude installed from Microsoft Store)
$storePkg = Get-ChildItem "$env:LOCALAPPDATA\Packages" -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "Claude_*" } | Select-Object -First 1
if ($storePkg) {
    $configDir = Join-Path $storePkg.FullName "LocalCache\Roaming\Claude"
    Write-Host "  Detected: Windows Store install at $configDir" -ForegroundColor Cyan
} else {
    # Regular installer path
    $configDir = Join-Path $env:APPDATA "Claude"
    Write-Host "  Detected: Standard install at $configDir" -ForegroundColor Cyan
}

New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$configPath = Join-Path $configDir "claude_desktop_config.json"

# Write clean UTF-8 without BOM — ConvertTo-Json / Set-Content add BOM which breaks Claude
# Use stdio transport — works on all Claude Desktop versions including Cowork/Store builds
$jsonContent = "{`r`n  ""mcpServers"": {`r`n    ""mcp-forge"": {`r`n      ""command"": ""$pythonExe"",`r`n      ""args"": [""$projectPath/mcp_server/server.py""],`r`n      ""env"": {`r`n        ""PYTHONPATH"": ""$projectPath"",`r`n        ""APP_URL"": ""http://localhost:8000"",`r`n        ""MCP_AUTH_TOKEN"": ""$token"",`r`n        ""MCP_TRANSPORT"": ""stdio""`r`n      }`r`n    }`r`n  }`r`n}"
[System.IO.File]::WriteAllText($configPath, $jsonContent, (New-Object System.Text.UTF8Encoding $false))

Write-Host "  Config written to: $configPath" -ForegroundColor Green

# Step 4: Done
Write-Host "[5/5] Done!" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host "  1. Fully QUIT Claude Desktop (system tray -> right-click -> Quit)"
Write-Host "  2. Reopen Claude Desktop"
Write-Host "  3. Go to Settings -> Developer -- look for mcp-forge with a green dot"
Write-Host "  4. Ask Claude: List all my MCP Forge projects"
Write-Host ""
