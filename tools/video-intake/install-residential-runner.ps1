param(
    [string]$Repository = 'amirdoit/txt-vido',
    [string]$RunnerRoot = "$env:LOCALAPPDATA\VirtalTikTok\github-runner-video-intake",
    [string]$RunnerVersion = '2.336.0'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

Write-Step 'Checking Windows prerequisites'
if ($env:OS -ne 'Windows_NT') {
    throw 'This installer is for the Windows desktop that has your normal residential internet connection.'
}

$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
if ($arch -ne 'X64') {
    throw "This installer currently expects Windows X64. Detected: $arch"
}

if (-not (Get-Command gh.exe -ErrorAction SilentlyContinue)) {
    Write-Step 'Installing GitHub CLI with winget'
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'GitHub CLI is not installed and winget is unavailable. Install GitHub CLI once, then rerun this script.'
    }
    & winget.exe install --id GitHub.cli --exact --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI installation failed.' }
    Refresh-Path
}

Write-Step 'Checking GitHub authentication'
& gh.exe auth status --hostname github.com 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'A GitHub browser login will open once. This is only for registering your private runner.' -ForegroundColor Yellow
    & gh.exe auth login --hostname github.com --git-protocol https --web --scopes 'repo,workflow'
    if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication failed.' }
}

Write-Step "Verifying admin access to $Repository"
$permission = (& gh.exe api "repos/$Repository/collaborators/amirdoit/permission" --jq '.permission').Trim()
if ($permission -notin @('admin','maintain')) {
    throw "The authenticated GitHub account does not have runner-management permission on $Repository. Permission: $permission"
}

Write-Step 'Preparing runner directory'
New-Item -ItemType Directory -Force -Path $RunnerRoot | Out-Null
$runnerConfig = Join-Path $RunnerRoot '.runner'

if (-not (Test-Path $runnerConfig)) {
    $zipName = "actions-runner-win-x64-$RunnerVersion.zip"
    $zipPath = Join-Path $env:TEMP $zipName
    $runnerUri = "https://github.com/actions/runner/releases/download/v$RunnerVersion/$zipName"

    Write-Step "Downloading GitHub Actions runner v$RunnerVersion"
    Invoke-WebRequest -Uri $runnerUri -OutFile $zipPath -UseBasicParsing

    Write-Step 'Extracting GitHub Actions runner'
    Get-ChildItem $RunnerRoot -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    Expand-Archive -Path $zipPath -DestinationPath $RunnerRoot -Force
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

    Write-Step 'Creating a short-lived runner registration token'
    $registrationToken = (& gh.exe api -X POST "repos/$Repository/actions/runners/registration-token" --jq '.token').Trim()
    if (-not $registrationToken) { throw 'GitHub did not return a runner registration token.' }

    $runnerName = "Amir-Video-Intake-$env:COMPUTERNAME"
    Write-Step "Registering runner: $runnerName"
    Push-Location $RunnerRoot
    try {
        & .\config.cmd `
            --url "https://github.com/$Repository" `
            --token $registrationToken `
            --name $runnerName `
            --labels 'video-intake' `
            --work '_work' `
            --unattended `
            --replace
        if ($LASTEXITCODE -ne 0) { throw 'GitHub runner configuration failed.' }
    }
    finally {
        Pop-Location
    }
} else {
    Write-Host 'Runner is already registered. Keeping the existing registration.' -ForegroundColor Green
}

Write-Step 'Installing automatic startup for the current Windows user'
$startupFolder = [Environment]::GetFolderPath('Startup')
$startupCmd = Join-Path $startupFolder 'VirtalTikTok-Video-Intake-Runner.cmd'
$runCmd = Join-Path $RunnerRoot 'run.cmd'
@
"@echo off
cd /d `"$RunnerRoot`"
call `"$runCmd`"
"@ | Set-Content -Path $startupCmd -Encoding ascii

Write-Step 'Starting the residential runner now'
$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($RunnerRoot) -and $_.Name -match 'Runner\.(Listener|Worker)|cmd.exe' }
if (-not $existing) {
    Start-Process -FilePath $runCmd -WorkingDirectory $RunnerRoot -WindowStyle Minimized
    Start-Sleep -Seconds 3
}

Write-Step 'Installing a project-local yt-dlp cache directory'
$intakeRoot = Join-Path $env:LOCALAPPDATA 'VirtalTikTok\video-intake'
New-Item -ItemType Directory -Force -Path $intakeRoot | Out-Null

Write-Host "`nResidential Video Intake runner is installed." -ForegroundColor Green
Write-Host "Repository: $Repository"
Write-Host "Runner folder: $RunnerRoot"
Write-Host "Startup entry: $startupCmd"
Write-Host ''
Write-Host 'What this changes:' -ForegroundColor Cyan
Write-Host '  • Future public video URLs can be fetched from your normal residential connection.'
Write-Host '  • The workflow tries public download first, so YouTube cookies are not required for normal public videos.'
Write-Host '  • If login is ever required, the workflow can use a local Firefox session or a local cookie file.'
Write-Host '  • Browser cookies are never committed to GitHub or uploaded as artifacts.'
Write-Host ''
Write-Host 'Keep this runner for the video project only. The workflow accepts only trusted same-repo requests from amirdoit.' -ForegroundColor Yellow
