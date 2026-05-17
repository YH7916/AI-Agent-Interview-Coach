param(
    [switch]$SkipTauriBuild
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Add-PathPrefix {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path $Path)) {
        return
    }
    $parts = $env:Path -split ';'
    if ($parts -contains $Path) {
        return
    }
    $env:Path = "$Path;$env:Path"
}

function Use-ProjectVirtualEnv {
    $venvScripts = Join-Path $ProjectRoot ".venv\Scripts"
    if (Test-Path (Join-Path $venvScripts "python.exe")) {
        Add-PathPrefix $venvScripts
        Write-Host "Using Python virtual environment: $venvScripts"
    }
}

function Use-ScoopRustEnvironment {
    $cargoHome = [Environment]::GetEnvironmentVariable("CARGO_HOME", "User")
    $rustupHome = [Environment]::GetEnvironmentVariable("RUSTUP_HOME", "User")
    if ($cargoHome) {
        $env:CARGO_HOME = $cargoHome
        Add-PathPrefix (Join-Path $cargoHome "bin")
    }
    if ($rustupHome) {
        $env:RUSTUP_HOME = $rustupHome
        $stableToolchain = Join-Path $rustupHome "toolchains\stable-x86_64-pc-windows-msvc"
        if (Test-Path $stableToolchain) {
            if (-not $env:RUSTUP_TOOLCHAIN) {
                $env:RUSTUP_TOOLCHAIN = "stable-x86_64-pc-windows-msvc"
            }
            Add-PathPrefix (Join-Path $stableToolchain "bin")
        }
    }
}

function Use-VisualStudioBuildTools {
    if (Get-Command cl -ErrorAction SilentlyContinue) {
        return
    }
    $vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        return
    }
    $vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vsPath) {
        return
    }
    $vcvars = Join-Path $vsPath "VC\Auxiliary\Build\vcvars64.bat"
    if (-not (Test-Path $vcvars)) {
        return
    }
    cmd /c "`"$vcvars`" >nul && set" | ForEach-Object {
        if ($_ -match "^(.*?)=(.*)$") {
            Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
        }
    }
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host "==> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Use-ProjectVirtualEnv
Use-ScoopRustEnvironment

Invoke-Step "ruff" { python -m ruff check . }
Invoke-Step "mypy" { python -m mypy oncall_app }
Invoke-Step "unit tests" { python -m unittest discover -v }
Invoke-Step "frontend lint" { npm run lint:frontend }
Invoke-Step "interview product eval" {
    python scripts\evaluate_interview_agent.py --suite all --json-out artifacts\evals\latest.json
}

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw "pyinstaller is not installed. Install dev dependencies before packaging."
}

Invoke-Step "pyinstaller sidecar" {
    pyinstaller packaging\pyinstaller\interview-agent-sidecar.spec --noconfirm
}

$targetTriple = "x86_64-pc-windows-msvc"
$binaryDir = Join-Path $ProjectRoot "desktop\src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $binaryDir | Out-Null
$sourceExe = Join-Path $ProjectRoot "dist\interview-agent-sidecar.exe"
$targetExe = Join-Path $binaryDir "interview-agent-sidecar-$targetTriple.exe"
if (-not (Test-Path $sourceExe)) {
    throw "Expected sidecar executable not found: $sourceExe"
}
Copy-Item -Force $sourceExe $targetExe

if (-not $SkipTauriBuild) {
    Invoke-Step "desktop dependencies" { npm --prefix desktop ci }
    Use-VisualStudioBuildTools
    Invoke-Step "tauri desktop build" { npm --prefix desktop run build }
}
