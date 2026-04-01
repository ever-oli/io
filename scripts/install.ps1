# ============================================================================
# IO Installer for Windows
# ============================================================================
# Installation script for Windows (PowerShell).
# Uses uv for fast Python provisioning and package management.
#
# Usage:
#   irm https://raw.githubusercontent.com/ever-oli/io/main/scripts/install.ps1 | iex
#
# Or download and run with options:
#   .\install.ps1 -NoVenv -SkipSetup
#
# ============================================================================

param(
    [switch]$NoVenv,
    [switch]$SkipSetup,
    [string]$Branch = "main",
    [string]$IOHome = "$env:LOCALAPPDATA\io",
    [string]$InstallDir = "$env:LOCALAPPDATA\io\io"
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Configuration
# ============================================================================

$RepoUrlSsh = "git@github.com:ever-oli/io.git"
$RepoUrlHttps = "https://github.com/ever-oli/io.git"
$PythonVersion = "3.11"
$NodeVersion = "22"

# ============================================================================
# Helper functions
# ============================================================================

function Write-Banner {
    Write-Host ""
    Write-Host "┌─────────────────────────────────────────────────────────┐" -ForegroundColor Magenta
    Write-Host "│                    IO Installer                         │" -ForegroundColor Magenta
    Write-Host "├─────────────────────────────────────────────────────────┤" -ForegroundColor Magenta
    Write-Host "│  An open source AI coding agent by ever-oli.            │" -ForegroundColor Magenta
    Write-Host "└─────────────────────────────────────────────────────────┘" -ForegroundColor Magenta
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "-> $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "+ $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "! $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "x $Message" -ForegroundColor Red
}

function Test-InteractiveTerminal {
    return [Environment]::UserInteractive
}

# ============================================================================
# Dependency checks
# ============================================================================

function Install-Uv {
    Write-Info "Checking for uv package manager..."

    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $script:UvCmd = "uv"
        $version = uv --version
        Write-Success "uv found ($version)"
        return $true
    }

    $uvPaths = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:USERPROFILE\.cargo\bin\uv.exe"
    )
    foreach ($uvPath in $uvPaths) {
        if (Test-Path $uvPath) {
            $script:UvCmd = $uvPath
            $version = & $uvPath --version
            Write-Success "uv found at $uvPath ($version)"
            return $true
        }
    }

    Write-Info "Installing uv (fast Python package manager)..."
    try {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" 2>&1 | Out-Null

        $uvExe = "$env:USERPROFILE\.local\bin\uv.exe"
        if (-not (Test-Path $uvExe)) {
            $uvExe = "$env:USERPROFILE\.cargo\bin\uv.exe"
        }
        if (-not (Test-Path $uvExe)) {
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
            if (Get-Command uv -ErrorAction SilentlyContinue) {
                $uvExe = (Get-Command uv).Source
            }
        }

        if (Test-Path $uvExe) {
            $script:UvCmd = $uvExe
            $version = & $uvExe --version
            Write-Success "uv installed ($version)"
            return $true
        }

        Write-Err "uv installed but not found on PATH"
        Write-Info "Try restarting your terminal and re-running"
        return $false
    } catch {
        Write-Err "Failed to install uv"
        Write-Info "Install manually: https://docs.astral.sh/uv/getting-started/installation/"
        return $false
    }
}

function Test-Python {
    Write-Info "Checking Python $PythonVersion..."

    try {
        $pythonPath = & $UvCmd python find $PythonVersion 2>$null
        if ($pythonPath) {
            $ver = & $pythonPath --version 2>$null
            Write-Success "Python found: $ver"
            return $true
        }
    } catch { }

    Write-Info "Python $PythonVersion not found, installing via uv..."
    try {
        & $UvCmd python install $PythonVersion 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $pythonPath = & $UvCmd python find $PythonVersion 2>$null
            if ($pythonPath) {
                $ver = & $pythonPath --version 2>$null
                Write-Success "Python installed: $ver"
                return $true
            }
        }
    } catch { }

    foreach ($fallbackVer in @("3.12", "3.13", "3.10")) {
        try {
            $pythonPath = & $UvCmd python find $fallbackVer 2>$null
            if ($pythonPath) {
                $ver = & $pythonPath --version 2>$null
                Write-Success "Found fallback: $ver"
                $script:PythonVersion = $fallbackVer
                return $true
            }
        } catch { }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $sysVer = python --version 2>$null
        if ($sysVer -match "3\.(1[0-9]|[1-9][0-9])") {
            Write-Success "Using system Python: $sysVer"
            return $true
        }
    }

    Write-Err "Failed to install Python $PythonVersion"
    Write-Info "Install Python 3.11 manually, then re-run this script:"
    Write-Info "  https://www.python.org/downloads/"
    Write-Info "  Or: winget install Python.Python.3.11"
    return $false
}

function Test-Git {
    Write-Info "Checking Git..."

    if (Get-Command git -ErrorAction SilentlyContinue) {
        $version = git --version
        Write-Success "Git found ($version)"
        return $true
    }

    Write-Err "Git not found"
    Write-Info "Please install Git from:"
    Write-Info "  https://git-scm.com/download/win"
    return $false
}

function Test-Node {
    Write-Info "Checking Node.js (for browser tools)..."

    if (Get-Command node -ErrorAction SilentlyContinue) {
        $version = node --version
        Write-Success "Node.js $version found"
        $script:HasNode = $true
        return $true
    }

    $managedNode = Join-Path $IOHome "node\node.exe"
    if (Test-Path $managedNode) {
        $version = & $managedNode --version
        $env:Path = "$(Split-Path $managedNode -Parent);$env:Path"
        Write-Success "Node.js $version found (IO-managed)"
        $script:HasNode = $true
        return $true
    }

    Write-Info "Node.js not found, installing Node.js $NodeVersion LTS..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Installing via winget..."
        try {
            winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
            if (Get-Command node -ErrorAction SilentlyContinue) {
                $version = node --version
                Write-Success "Node.js $version installed via winget"
                $script:HasNode = $true
                return $true
            }
        } catch { }
    }

    Write-Info "Downloading Node.js $NodeVersion binary..."
    try {
        $arch = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
        $indexUrl = "https://nodejs.org/dist/latest-v${NodeVersion}.x/"
        $indexPage = Invoke-WebRequest -Uri $indexUrl -UseBasicParsing
        $zipName = ($indexPage.Content | Select-String -Pattern "node-v${NodeVersion}\.\d+\.\d+-win-${arch}\.zip" -AllMatches).Matches[0].Value

        if ($zipName) {
            $downloadUrl = "${indexUrl}${zipName}"
            $tmpZip = Join-Path $env:TEMP $zipName
            $tmpDir = Join-Path $env:TEMP "io-node-extract"

            Invoke-WebRequest -Uri $downloadUrl -OutFile $tmpZip -UseBasicParsing
            if (Test-Path $tmpDir) { Remove-Item -Recurse -Force $tmpDir }
            Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force

            $extractedDir = Get-ChildItem $tmpDir -Directory | Select-Object -First 1
            if ($extractedDir) {
                if (Test-Path "$IOHome\node") { Remove-Item -Recurse -Force "$IOHome\node" }
                Move-Item $extractedDir.FullName "$IOHome\node"
                $env:Path = "$IOHome\node;$env:Path"

                $version = & "$IOHome\node\node.exe" --version
                Write-Success "Node.js $version installed to ~/.io/node/"
                $script:HasNode = $true

                Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue
                Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
                return $true
            }
        }
    } catch {
        Write-Warn "Download failed: $_"
    }

    Write-Warn "Could not auto-install Node.js"
    Write-Info "Install manually: https://nodejs.org/en/download/"
    $script:HasNode = $false
    return $true
}

function Install-SystemPackages {
    $script:HasRipgrep = $false
    $script:HasFfmpeg = $false
    $needRipgrep = $false
    $needFfmpeg = $false

    Write-Info "Checking ripgrep (fast file search)..."
    if (Get-Command rg -ErrorAction SilentlyContinue) {
        $version = rg --version | Select-Object -First 1
        Write-Success "$version found"
        $script:HasRipgrep = $true
    } else {
        $needRipgrep = $true
    }

    Write-Info "Checking ffmpeg (TTS voice messages)..."
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        Write-Success "ffmpeg found"
        $script:HasFfmpeg = $true
    } else {
        $needFfmpeg = $true
    }

    if (-not $needRipgrep -and -not $needFfmpeg) { return }

    $descParts = @()
    $wingetPkgs = @()
    $chocoPkgs = @()
    $scoopPkgs = @()

    if ($needRipgrep) {
        $descParts += "ripgrep for faster file search"
        $wingetPkgs += "BurntSushi.ripgrep.MSVC"
        $chocoPkgs += "ripgrep"
        $scoopPkgs += "ripgrep"
    }
    if ($needFfmpeg) {
        $descParts += "ffmpeg for TTS voice messages"
        $wingetPkgs += "Gyan.FFmpeg"
        $chocoPkgs += "ffmpeg"
        $scoopPkgs += "ffmpeg"
    }

    $description = $descParts -join " and "
    $hasWinget = Get-Command winget -ErrorAction SilentlyContinue
    $hasChoco = Get-Command choco -ErrorAction SilentlyContinue
    $hasScoop = Get-Command scoop -ErrorAction SilentlyContinue

    if ($hasWinget) {
        Write-Info "Installing $description via winget..."
        foreach ($pkg in $wingetPkgs) {
            try {
                winget install $pkg --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
            } catch { }
        }
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
        if ($needRipgrep -and (Get-Command rg -ErrorAction SilentlyContinue)) {
            Write-Success "ripgrep installed"
            $script:HasRipgrep = $true
            $needRipgrep = $false
        }
        if ($needFfmpeg -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Success "ffmpeg installed"
            $script:HasFfmpeg = $true
            $needFfmpeg = $false
        }
        if (-not $needRipgrep -and -not $needFfmpeg) { return }
    }

    if ($hasChoco -and ($needRipgrep -or $needFfmpeg)) {
        Write-Info "Trying Chocolatey..."
        foreach ($pkg in $chocoPkgs) {
            try { choco install $pkg -y 2>&1 | Out-Null } catch { }
        }
        if ($needRipgrep -and (Get-Command rg -ErrorAction SilentlyContinue)) {
            Write-Success "ripgrep installed via chocolatey"
            $script:HasRipgrep = $true
            $needRipgrep = $false
        }
        if ($needFfmpeg -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Success "ffmpeg installed via chocolatey"
            $script:HasFfmpeg = $true
            $needFfmpeg = $false
        }
    }

    if ($hasScoop -and ($needRipgrep -or $needFfmpeg)) {
        Write-Info "Trying Scoop..."
        foreach ($pkg in $scoopPkgs) {
            try { scoop install $pkg 2>&1 | Out-Null } catch { }
        }
        if ($needRipgrep -and (Get-Command rg -ErrorAction SilentlyContinue)) {
            Write-Success "ripgrep installed via scoop"
            $script:HasRipgrep = $true
            $needRipgrep = $false
        }
        if ($needFfmpeg -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Success "ffmpeg installed via scoop"
            $script:HasFfmpeg = $true
            $needFfmpeg = $false
        }
    }

    if ($needRipgrep) {
        Write-Warn "ripgrep not installed (file search will use findstr fallback)"
        Write-Info "  winget install BurntSushi.ripgrep.MSVC"
    }
    if ($needFfmpeg) {
        Write-Warn "ffmpeg not installed (TTS voice messages will be limited)"
        Write-Info "  winget install Gyan.FFmpeg"
    }
}

# ============================================================================
# Installation
# ============================================================================

function Install-Repository {
    Write-Info "Installing to $InstallDir..."

    if (Test-Path $InstallDir) {
        if (-not (Test-Path "$InstallDir\.git")) {
            Write-Err "Directory exists but is not a git repository: $InstallDir"
            Write-Info "Remove it or choose a different directory with -InstallDir"
            throw "Directory exists but is not a git repository"
        }

        Write-Info "Existing installation found, updating..."
        Push-Location $InstallDir
        $autoStashRef = ""
        $status = git status --porcelain
        if ($status) {
            $stashName = "io-install-autostash-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
            Write-Info "Local changes detected, stashing before update..."
            git stash push --include-untracked -m $stashName | Out-Null
            $autoStashRef = (git rev-parse --verify refs/stash 2>$null)
        }

        git -c windows.appendAtomically=false fetch origin
        git -c windows.appendAtomically=false checkout $Branch
        git -c windows.appendAtomically=false pull --ff-only origin $Branch

        if ($autoStashRef) {
            $restoreNow = $true
            if (Test-InteractiveTerminal) {
                Write-Host ""
                Write-Warn "Local changes were stashed before updating."
                Write-Warn "Restoring them may reapply local customizations onto the updated codebase."
                $response = Read-Host "Restore local changes now? [Y/n]"
                if ($response -and $response -notmatch '^(?i:y|yes)$') {
                    $restoreNow = $false
                }
            }

            if ($restoreNow) {
                Write-Info "Restoring local changes..."
                git stash apply $autoStashRef | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    git stash drop $autoStashRef | Out-Null
                    Write-Warn "Local changes were restored on top of the updated codebase."
                    Write-Warn "Review git diff / git status if IO behaves unexpectedly."
                } else {
                    throw "Update succeeded, but restoring local changes failed. Your changes are still preserved in git stash."
                }
            } else {
                Write-Info "Skipped restoring local changes."
                Write-Info "Your changes are still preserved in git stash."
                Write-Info "Restore manually with: git stash apply $autoStashRef"
            }
        }
        Pop-Location
    } else {
        $cloneSuccess = $false

        Write-Info "Configuring git for Windows compatibility..."
        $env:GIT_CONFIG_COUNT = "1"
        $env:GIT_CONFIG_KEY_0 = "windows.appendAtomically"
        $env:GIT_CONFIG_VALUE_0 = "false"
        git config --global windows.appendAtomically false 2>$null

        Write-Info "Trying SSH clone..."
        $env:GIT_SSH_COMMAND = "ssh -o BatchMode=yes -o ConnectTimeout=5"
        try {
            git -c windows.appendAtomically=false clone --branch $Branch $RepoUrlSsh $InstallDir
            if ($LASTEXITCODE -eq 0) { $cloneSuccess = $true }
        } catch { }
        $env:GIT_SSH_COMMAND = $null

        if (-not $cloneSuccess) {
            if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue }
            Write-Info "SSH failed, trying HTTPS..."
            try {
                git -c windows.appendAtomically=false clone --branch $Branch $RepoUrlHttps $InstallDir
                if ($LASTEXITCODE -eq 0) { $cloneSuccess = $true }
            } catch { }
        }

        if (-not $cloneSuccess) {
            if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue }
            Write-Warn "Git clone failed, downloading ZIP archive instead..."
            try {
                $zipUrl = "https://github.com/ever-oli/io/archive/refs/heads/$Branch.zip"
                $zipPath = Join-Path $env:TEMP "io-$Branch.zip"
                $extractPath = Join-Path $env:TEMP "io-extract"

                Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
                if (Test-Path $extractPath) { Remove-Item -Recurse -Force $extractPath }
                Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

                $extractedDir = Get-ChildItem $extractPath -Directory | Select-Object -First 1
                if ($extractedDir) {
                    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
                    Move-Item $extractedDir.FullName $InstallDir -Force
                    Write-Success "Downloaded and extracted"

                    Push-Location $InstallDir
                    git -c windows.appendAtomically=false init 2>$null
                    git -c windows.appendAtomically=false config windows.appendAtomically false 2>$null
                    git remote add origin $RepoUrlHttps 2>$null
                    Pop-Location
                    Write-Success "Git repo initialized for future updates"

                    $cloneSuccess = $true
                }

                Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
                Remove-Item -Recurse -Force $extractPath -ErrorAction SilentlyContinue
            } catch {
                Write-Err "ZIP download also failed: $_"
            }
        }

        if (-not $cloneSuccess) {
            throw "Failed to download repository (tried git clone SSH, HTTPS, and ZIP)"
        }
    }

    Push-Location $InstallDir
    git -c windows.appendAtomically=false config windows.appendAtomically false 2>$null

    Write-Info "Initializing mini-swe-agent submodule (terminal backend)..."
    git -c windows.appendAtomically=false submodule update --init mini-swe-agent 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "mini-swe-agent init failed (terminal tools may need manual setup)"
    } else {
        Write-Success "Submodule ready"
    }
    Pop-Location

    Write-Success "Repository ready"
}

function Install-Venv {
    if ($NoVenv) {
        Write-Info "Skipping virtual environment (-NoVenv)"
        return
    }

    Write-Info "Creating virtual environment with Python $PythonVersion..."
    Push-Location $InstallDir
    if (Test-Path "venv") {
        Write-Info "Virtual environment already exists, recreating..."
        Remove-Item -Recurse -Force "venv"
    }
    & $UvCmd venv venv --python $PythonVersion
    Pop-Location

    Write-Success "Virtual environment ready (Python $PythonVersion)"
}

function Install-Dependencies {
    Write-Info "Installing dependencies..."
    Push-Location $InstallDir

    if (-not $NoVenv) {
        $env:VIRTUAL_ENV = "$InstallDir\venv"
    }

    try {
        & $UvCmd pip install -e ".[all]" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "full install failed" }
    } catch {
        Write-Warn "Full install (.[all]) failed, trying base install..."
        & $UvCmd pip install -e "." 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Pop-Location
            throw "Package installation failed"
        }
    }

    Write-Success "Main package installed"

    Write-Info "Installing mini-swe-agent (terminal tool backend)..."
    if (Test-Path "mini-swe-agent\pyproject.toml") {
        try {
            & $UvCmd pip install -e ".\mini-swe-agent" 2>&1 | Out-Null
            Write-Success "mini-swe-agent installed"
        } catch {
            Write-Warn "mini-swe-agent install failed (terminal tools may not work)"
        }
    } else {
        Write-Warn "mini-swe-agent not found (run: git submodule update --init mini-swe-agent)"
    }

    if (Test-Path "tinker-atropos\pyproject.toml") {
        Write-Info "tinker-atropos submodule found, skipping install (optional, for RL training)"
        Write-Info "  To install: $UvCmd pip install -e .\tinker-atropos"
    }

    Pop-Location
    Write-Success "All dependencies installed"
}

function Set-PathVariable {
    Write-Info "Setting up io command..."

    if ($NoVenv) {
        $ioCmd = (Get-Command io -ErrorAction SilentlyContinue)
        if (-not $ioCmd) {
            Write-Warn "io not found on PATH after install"
            return
        }
        $ioBin = Split-Path $ioCmd.Source -Parent
        $ioExe = $ioCmd.Source
    } else {
        $ioBin = "$InstallDir\venv\Scripts"
        $ioExe = "$ioBin\io.exe"
        if (-not (Test-Path $ioExe)) {
            Write-Warn "io entry point not found at $ioExe"
            Write-Info "This usually means the pip install did not complete successfully."
            Write-Info "Try: cd $InstallDir && uv pip install -e '.[all]'"
            return
        }
    }

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$ioBin*") {
        [Environment]::SetEnvironmentVariable("Path", "$ioBin;$currentPath", "User")
        Write-Success "Added to user PATH: $ioBin"
    } else {
        Write-Info "PATH already configured"
    }

    $currentIOHome = [Environment]::GetEnvironmentVariable("IO_HOME", "User")
    if (-not $currentIOHome -or $currentIOHome -ne $IOHome) {
        [Environment]::SetEnvironmentVariable("IO_HOME", $IOHome, "User")
        Write-Success "Set IO_HOME=$IOHome"
    }

    $env:IO_HOME = $IOHome
    $env:Path = "$ioBin;$env:Path"

    Write-Success "io command ready"
}

function Copy-ConfigTemplates {
    Write-Info "Setting up configuration files..."

    foreach ($path in @(
        "$IOHome\cron",
        "$IOHome\sessions",
        "$IOHome\logs",
        "$IOHome\pairing",
        "$IOHome\hooks",
        "$IOHome\image_cache",
        "$IOHome\audio_cache",
        "$IOHome\memories",
        "$IOHome\skills",
        "$IOHome\whatsapp\session"
    )) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }

    $envPath = "$IOHome\.env"
    if (-not (Test-Path $envPath)) {
        $examplePath = "$InstallDir\.env.example"
        if (Test-Path $examplePath) {
            Copy-Item $examplePath $envPath
            Write-Success "Created ~/.io/.env from template"
        } else {
            New-Item -ItemType File -Force -Path $envPath | Out-Null
            Write-Success "Created ~/.io/.env"
        }
    } else {
        Write-Info "~/.io/.env already exists, keeping it"
    }

    $configPath = "$IOHome\config.yaml"
    if (-not (Test-Path $configPath)) {
        $examplePath = "$InstallDir\cli-config.yaml.example"
        if (Test-Path $examplePath) {
            Copy-Item $examplePath $configPath
            Write-Success "Created ~/.io/config.yaml from template"
        }
    } else {
        Write-Info "~/.io/config.yaml already exists, keeping it"
    }

    $soulPath = "$IOHome\SOUL.md"
    if (-not (Test-Path $soulPath)) {
        @"
# IO Persona

<!--
This file defines the agent's personality and tone.
The agent will embody whatever you write here.
Edit this to customize how IO communicates with you.

Examples:
  - "You are a warm, playful assistant who uses kaomoji occasionally."
  - "You are a concise technical expert. No fluff, just facts."
  - "You speak like a friendly coworker who happens to know everything."

This file is loaded fresh each message -- no restart needed.
Delete the contents (or this file) to use the default personality.
-->
"@ | Set-Content -Path $soulPath -Encoding UTF8
        Write-Success "Created ~/.io/SOUL.md (edit to customize personality)"
    }

    Write-Success "Configuration directory ready: ~/.io/"

    $pythonExe = "$InstallDir\venv\Scripts\python.exe"
    if (Test-Path $pythonExe) {
        Write-Info "Syncing bundled skills to ~/.io/skills/ ..."
        try {
            & $pythonExe "$InstallDir\tools\skills_sync.py" 2>$null
            Write-Success "Skills synced to ~/.io/skills/"
        } catch {
            $bundledSkills = "$InstallDir\skills"
            $userSkills = "$IOHome\skills"
            if ((Test-Path $bundledSkills) -and -not (Get-ChildItem $userSkills -Exclude '.bundled_manifest' -ErrorAction SilentlyContinue)) {
                Copy-Item -Path "$bundledSkills\*" -Destination $userSkills -Recurse -Force -ErrorAction SilentlyContinue
                Write-Success "Skills copied to ~/.io/skills/"
            }
        }
    }
}

function Install-NodeDeps {
    if (-not $HasNode) {
        Write-Info "Skipping Node.js dependencies (Node not installed)"
        return
    }

    Push-Location $InstallDir

    if (Test-Path "package.json") {
        Write-Info "Installing Node.js dependencies (browser tools)..."
        try {
            npm install --silent 2>&1 | Out-Null
            Write-Success "Node.js dependencies installed"
        } catch {
            Write-Warn "npm install failed (browser tools may not work)"
        }

        Write-Info "Installing browser engine (Playwright Chromium)..."
        try {
            npx playwright install chromium 2>&1 | Out-Null
            Write-Success "Browser engine installed"
        } catch {
            Write-Warn "Playwright browser install failed (browser tools may not work)"
        }
    }

    $bridgeDir = "$InstallDir\scripts\whatsapp-bridge"
    if (Test-Path "$bridgeDir\package.json") {
        Write-Info "Installing WhatsApp bridge dependencies..."
        Push-Location $bridgeDir
        try {
            npm install --silent 2>&1 | Out-Null
            Write-Success "WhatsApp bridge dependencies installed"
        } catch {
            Write-Warn "WhatsApp bridge npm install failed (WhatsApp may not work)"
        }
        Pop-Location
    }

    Pop-Location
}

function Show-PostInstallGuidance {
    if ($SkipSetup) {
        Write-Info "Skipping post-install setup guidance (-SkipSetup)"
        return
    }

    Write-Host ""
    Write-Info "Next steps:"
    Write-Host ""
    Write-Info "1. Add provider credentials in ~/.io/.env"
    Write-Info "2. Optionally adjust model/provider defaults in ~/.io/config.yaml"
    Write-Info "3. Start IO with: io"
}

function Start-GatewayIfConfigured {
    $envPath = "$IOHome\.env"
    if (-not (Test-Path $envPath)) { return }

    $hasMessaging = $false
    $content = Get-Content $envPath -ErrorAction SilentlyContinue
    foreach ($var in @("TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "WHATSAPP_ENABLED")) {
        $match = $content | Where-Object { $_ -match "^${var}=.+" -and $_ -notmatch "your-token-here" }
        if ($match) { $hasMessaging = $true; break }
    }
    if (-not $hasMessaging) { return }

    Write-Host ""
    Write-Info "Messaging platform token detected!"
    Write-Info "The gateway needs to be running for IO to send and receive messages."

    $ioCmd = "$InstallDir\venv\Scripts\io.exe"
    if (-not (Test-Path $ioCmd)) {
        $ioCmd = "io"
    }

    $whatsappEnabled = $content | Where-Object { $_ -match "^WHATSAPP_ENABLED=true" }
    $whatsappSession = "$IOHome\whatsapp\session\creds.json"
    if ($whatsappEnabled -and -not (Test-Path $whatsappSession) -and (Test-InteractiveTerminal)) {
        Write-Host ""
        Write-Info "WhatsApp is enabled but not yet paired."
        Write-Info "Running 'io whatsapp' to pair via QR code..."
        Write-Host ""
        $response = Read-Host "Pair WhatsApp now? [Y/n]"
        if (-not $response -or $response -match "^[Yy]") {
            try { & $ioCmd whatsapp } catch { }
        }
    }

    if (-not (Test-InteractiveTerminal)) {
        Write-Info "Gateway setup skipped (no terminal available). Run 'io gateway install' later."
        return
    }

    Write-Host ""
    $response = Read-Host "Would you like to start the gateway now? [Y/n]"
    if (-not $response -or $response -match "^[Yy]") {
        Write-Info "Starting gateway in background..."
        try {
            $logFile = "$IOHome\logs\gateway.log"
            Start-Process -FilePath $ioCmd -ArgumentList "gateway", "run" `
                -RedirectStandardOutput $logFile `
                -RedirectStandardError "$IOHome\logs\gateway-error.log" `
                -WindowStyle Hidden
            Write-Success "Gateway started! Your bot is now online."
            Write-Info "Logs: $logFile"
            Write-Info "To stop: close the gateway process from Task Manager"
        } catch {
            Write-Warn "Failed to start gateway. Run manually: io gateway run"
        }
    } else {
        Write-Info "Skipped. Start the gateway later with: io gateway run"
    }
}

function Write-Completion {
    Write-Host ""
    Write-Host "┌─────────────────────────────────────────────────────────┐" -ForegroundColor Green
    Write-Host "│               Installation Complete!                   │" -ForegroundColor Green
    Write-Host "└─────────────────────────────────────────────────────────┘" -ForegroundColor Green
    Write-Host ""

    Write-Host "Your files (all in ~/.io/):" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   Config:    " -NoNewline -ForegroundColor Yellow
    Write-Host "$IOHome\config.yaml"
    Write-Host "   API Keys:  " -NoNewline -ForegroundColor Yellow
    Write-Host "$IOHome\.env"
    Write-Host "   Data:      " -NoNewline -ForegroundColor Yellow
    Write-Host "$IOHome\cron\, sessions\, logs\"
    Write-Host "   Code:      " -NoNewline -ForegroundColor Yellow
    Write-Host "$IOHome\io\"
    Write-Host ""

    Write-Host "─────────────────────────────────────────────────────────" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   io                " -NoNewline -ForegroundColor Green
    Write-Host "Start chatting"
    Write-Host "   io auth status    " -NoNewline -ForegroundColor Green
    Write-Host "Check provider auth status"
    Write-Host "   io config         " -NoNewline -ForegroundColor Green
    Write-Host "View/edit configuration"
    Write-Host "   io gateway install" -NoNewline -ForegroundColor Green
    Write-Host " Install gateway service scope"
    Write-Host "   io update         " -NoNewline -ForegroundColor Green
    Write-Host "Update to latest version"
    Write-Host ""

    Write-Host "─────────────────────────────────────────────────────────" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Restart your terminal for PATH changes to take effect" -ForegroundColor Yellow
    Write-Host ""

    if (-not $HasNode) {
        Write-Host "Note: Node.js could not be installed automatically." -ForegroundColor Yellow
        Write-Host "Browser tools need Node.js. Install manually:" -ForegroundColor Yellow
        Write-Host "  https://nodejs.org/en/download/" -ForegroundColor Yellow
        Write-Host ""
    }

    if (-not $HasRipgrep) {
        Write-Host "Note: ripgrep (rg) was not installed. For faster file search:" -ForegroundColor Yellow
        Write-Host "  winget install BurntSushi.ripgrep.MSVC" -ForegroundColor Yellow
        Write-Host ""
    }
}

# ============================================================================
# Main
# ============================================================================

function Main {
    Write-Banner

    if (-not (Install-Uv)) { throw "uv installation failed; cannot continue" }
    if (-not (Test-Python)) { throw "Python $PythonVersion not available; cannot continue" }
    if (-not (Test-Git)) { throw "Git not found; install from https://git-scm.com/download/win" }
    Test-Node
    Install-SystemPackages

    Install-Repository
    Install-Venv
    Install-Dependencies
    Install-NodeDeps
    Set-PathVariable
    Copy-ConfigTemplates
    Show-PostInstallGuidance
    Start-GatewayIfConfigured

    Write-Completion
}

try {
    Main
} catch {
    Write-Host ""
    Write-Err "Installation failed: $_"
    Write-Host ""
    Write-Info "If the error is unclear, try downloading and running the script directly:"
    Write-Host "  Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/ever-oli/io/main/scripts/install.ps1' -OutFile install.ps1" -ForegroundColor Yellow
    Write-Host "  .\install.ps1" -ForegroundColor Yellow
    Write-Host ""
}
