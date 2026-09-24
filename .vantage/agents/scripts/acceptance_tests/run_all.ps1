#!/usr/bin/env pwsh
Write-Host "Running all acceptance tests..."
pushd (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
./test_policy_smoke.ps1
./test_policy_blocking.ps1
./simulate_selection.ps1
popd | Out-Null
