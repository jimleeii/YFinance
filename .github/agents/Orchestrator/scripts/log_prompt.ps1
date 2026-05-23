param(
    [Parameter(Mandatory=$true)][string]$Command,
    [Parameter(Mandatory=$false)][string]$Message,
    [Parameter(Mandatory=$false)][string]$Author
)

$scriptPath = Join-Path $PSScriptRoot "log_prompt.py"
$py = "python"

$argsList = @($Command)
if ($Message) { $argsList += $Message }
if ($Author) { $argsList += "--author"; $argsList += $Author }

& $py $scriptPath @argsList

exit $LASTEXITCODE
