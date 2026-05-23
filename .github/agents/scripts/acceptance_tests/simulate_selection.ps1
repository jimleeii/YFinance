#!/usr/bin/env pwsh
Set-StrictMode -Version Latest

function Select-Model($models, $criticality) {
    # models: array of hashtables with keys: id, tier, toolCalling (bool), contextWindow (int), recentSuccess (int)
    # criticality: P0..P3
    $minTier = switch ($criticality) {
        'P0' { 'frontier' }
        'P1' { 'balanced' }
        'P2' { 'balanced' }
        default { 'economy' }
    }

    # filter capability
    $eligible = @($models | Where-Object { $_.toolCalling -eq $true -and $_.contextWindow -ge 2048 })

    # tier order
    $tierOrder = @('frontier','balanced','economy')

    # ensure minimum tier (allow tiers equal or higher than minimum)
    $minIndex = $tierOrder.IndexOf($minTier)
    $candidates = @($eligible | Where-Object { $tierOrder.IndexOf($_.tier) -le $minIndex })

    # choose highest recentSuccess, fallback to tier order
    if ($candidates.Count -gt 0) {
        $sorted = $candidates | Sort-Object @{Expression={$_.recentSuccess};Descending=$true}, @{Expression={$tierOrder.IndexOf($_.tier)};Ascending=$true}
        return @{ status='selected'; model=$sorted[0].id }
    }

    return @{ status='none' }
}

function Run-Scenario($name, $catalog1, $catalog2, $criticality, $expect) {
    Write-Host "Scenario: $name"
    $r1 = Select-Model $catalog1 $criticality
    if ($r1.status -eq 'selected') {
        Write-Host " -> selected (first discovery): $($r1.model)"
        if ($expect -ne $r1.model) { throw "Unexpected selection: $($r1.model) (expected $expect)" }
        return
    }
    Write-Host " -> no eligible model in first discovery, retrying discovery..."
    $r2 = Select-Model $catalog2 $criticality
    if ($r2.status -eq 'selected') {
        Write-Host " -> selected (after retry): $($r2.model)"
        if ($expect -ne $r2.model) { throw "Unexpected selection after retry: $($r2.model) (expected $expect)" }
        return
    }
    Write-Host " -> still no eligible model -> blocked"
    if ($expect -ne 'blocked') { throw "Unexpected blocked result (expected $expect)" }
}

# Scenario 1: frontier available
$catalogA1 = @(
    [PSCustomObject]@{ id='gpt-front'; tier='frontier'; toolCalling=$true; contextWindow=8192; recentSuccess=10 },
    [PSCustomObject]@{ id='gpt-bal'; tier='balanced'; toolCalling=$true; contextWindow=4096; recentSuccess=8 }
)
$catalogA2 = $catalogA1
Run-Scenario 'Frontier available' $catalogA1 $catalogA2 'P1' 'gpt-front'

# Scenario 2: frontier missing, balanced available on retry
$catalogB1 = @(
    [PSCustomObject]@{ id='gpt-econ'; tier='economy'; toolCalling=$true; contextWindow=4096; recentSuccess=20 }
)
$catalogB2 = @(
    [PSCustomObject]@{ id='gpt-bal-2'; tier='balanced'; toolCalling=$true; contextWindow=4096; recentSuccess=5 }
)
Run-Scenario 'Balanced on retry' $catalogB1 $catalogB2 'P1' 'gpt-bal-2'

# Scenario 3: none available -> blocked
$catalogC1 = @(
    [PSCustomObject]@{ id='gpt-econ'; tier='economy'; toolCalling=$false; contextWindow=1024; recentSuccess=1 }
)
$catalogC2 = @(
    [PSCustomObject]@{ id='gpt-econ2'; tier='economy'; toolCalling=$false; contextWindow=1024; recentSuccess=0 }
)
Run-Scenario 'No eligible -> blocked' $catalogC1 $catalogC2 'P0' 'blocked'

Write-Host "All simulation scenarios passed." -ForegroundColor Green
