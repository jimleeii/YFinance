#!/usr/bin/env pwsh
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir '..\..')
$base = $repoRoot.Path
$global:errors = @()

Write-Host "Running blocking/escalation policy tests against $base"

function Check-Contains($path, $pattern, $name) {
    $full = Join-Path $base $path
    if (-not (Test-Path $full)) {
        $global:errors += "Missing file: $path ($name)"
        return
    }
    $content = Get-Content $full -Raw
    if ($content -match [regex]::Escape($pattern)) {
        Write-Host "[PASS] $name"
    } else {
        Write-Host "[FAIL] $name - pattern not found"
        $global:errors += "${name}: pattern not found -> '$pattern'"
    }
}

# Check escalation flow phrases
Check-Contains 'rules/Model.Policy.md' 'Re-run discovery once to refresh availability and telemetry' 'Escalation - discovery refresh'
Check-Contains 'rules/Model.Policy.md' 'Retry selection once' 'Escalation - retry selection'
Check-Contains 'rules/Model.Policy.md' 'return a `blocked` status' 'Escalation - blocked status'
Check-Contains 'rules/Model.Policy.md' 'safe_override_option' 'Escalation - safe_override_option'

# Check override policy phrases
Check-Contains 'rules/Model.Policy.md' 'Tier overrides require explicit user phrase' 'Override policy - explicit phrase'
Check-Contains 'rules/Model.Policy.md' 'approve temporary tier override for this run' 'Override policy - approve phrase'

if ($global:errors.Count -eq 0) {
    Write-Host "Blocking/escalation tests passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host "Blocking/escalation Failures:`n" -ForegroundColor Red
    $global:errors | ForEach-Object { Write-Host " - $_" }
    exit 1
}
