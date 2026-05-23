#!/usr/bin/env pwsh
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir '..\..')
$base = $repoRoot.Path
$global:errors = @()

Write-Host "Running policy smoke tests against $base"

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

# Test 1: Routing classification presence
Check-Contains 'rules/Routing.Policy.md' 'Classify requests into `direct`, `single-agent`, or `multi-agent`' 'Routing classification'

# Test 2: Logging levels mapping
Check-Contains 'rules/Logging.Policy.md' '`minimal`: used for direct/simple responses' 'Logging levels - minimal'
Check-Contains 'rules/Logging.Policy.md' '`compact`: single-agent cycles' 'Logging levels - compact'
Check-Contains 'rules/Logging.Policy.md' '`full`: multi-agent cycles' 'Logging levels - full'

# Test 3: Model selection formula presence
Check-Contains 'rules/Model.Policy.md' 'selection_score = w_quality * quality_score' 'Model selection formula'

# Test 4: Global setting max_orchestration_cycles
Check-Contains 'Orchestrator.Agent.md' 'max_orchestration_cycles' 'Global setting: max_orchestration_cycles'

if ($global:errors.Count -eq 0) {
    Write-Host "All tests passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host "Failures:`n" -ForegroundColor Red
    $global:errors | ForEach-Object { Write-Host " - $_" }
    exit 1
}
