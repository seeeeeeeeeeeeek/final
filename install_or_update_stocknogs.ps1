param(
    [string]$TargetDir = (Join-Path $HOME "Desktop\stocknogs"),
    [string]$RepoUrl = "https://github.com/seeeeeeeeeeeeek/final.git",
    [string]$Branch = "main",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[stocknogs] $Message"
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $commandText = "git " + ($Arguments -join " ")
    if ($WorkingDirectory) {
        Write-Step "$commandText (in $WorkingDirectory)"
    }
    else {
        Write-Step $commandText
    }

    if ($DryRun) {
        return ""
    }

    if ($WorkingDirectory) {
        Push-Location $WorkingDirectory
    }
    try {
        $output = & git @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw ($output | Out-String).Trim()
        }
        return ($output | Out-String).Trim()
    }
    finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

function Ensure-GitInstalled {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git is required. Install Git or GitHub Desktop first, then run this script again."
    }
}

function Backup-ExistingFolder {
    param([Parameter(Mandatory = $true)][string]$PathToBackup)

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupPath = "${PathToBackup}_backup_${timestamp}"
    Write-Step "Existing folder is not the expected repo. Moving it to $backupPath"
    if (-not $DryRun) {
        Move-Item -LiteralPath $PathToBackup -Destination $backupPath
    }
    return $backupPath
}

Ensure-GitInstalled

$resolvedTarget = [System.IO.Path]::GetFullPath($TargetDir)
$gitDir = Join-Path $resolvedTarget ".git"

Write-Step "Target folder: $resolvedTarget"
Write-Step "Repository: $RepoUrl"
Write-Step "Branch: $Branch"

if (-not (Test-Path $resolvedTarget)) {
    Write-Step "Target folder does not exist. Cloning a fresh copy."
    Invoke-Git -Arguments @("clone", "--branch", $Branch, $RepoUrl, $resolvedTarget)
    Write-Step "Done. stocknogs is ready at $resolvedTarget"
    exit 0
}

if (Test-Path $gitDir) {
    $existingRemote = Invoke-Git -Arguments @("remote", "get-url", "origin") -WorkingDirectory $resolvedTarget
    if ($existingRemote -and $existingRemote.Trim().ToLowerInvariant() -ne $RepoUrl.Trim().ToLowerInvariant()) {
        Backup-ExistingFolder -PathToBackup $resolvedTarget | Out-Null
        Invoke-Git -Arguments @("clone", "--branch", $Branch, $RepoUrl, $resolvedTarget)
        Write-Step "Done. stocknogs is ready at $resolvedTarget"
        exit 0
    }

    Write-Step "Existing stocknogs repo found. Replacing local contents with the latest remote main branch."
    Invoke-Git -Arguments @("fetch", "origin") -WorkingDirectory $resolvedTarget
    Invoke-Git -Arguments @("checkout", $Branch) -WorkingDirectory $resolvedTarget
    Invoke-Git -Arguments @("reset", "--hard", "origin/$Branch") -WorkingDirectory $resolvedTarget
    Invoke-Git -Arguments @("clean", "-fd") -WorkingDirectory $resolvedTarget
    Write-Step "Done. stocknogs is now synced to origin/$Branch at $resolvedTarget"
    exit 0
}

Backup-ExistingFolder -PathToBackup $resolvedTarget | Out-Null
Invoke-Git -Arguments @("clone", "--branch", $Branch, $RepoUrl, $resolvedTarget)
Write-Step "Done. stocknogs is ready at $resolvedTarget"
