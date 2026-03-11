param(
  [Parameter(Mandatory = $true, Position = 0)][string]$InputJson,
  [Parameter(Mandatory = $true, Position = 1)][string]$OutputPrefix
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$tool = Join-Path $scriptDir "xbs_tool.py"

function Resolve-Python {
  if (Get-Command py -ErrorAction SilentlyContinue) { return @("py", "-3") }
  if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
  throw "Python 3 not found. Install Python and ensure 'py' or 'python' is in PATH."
}

$python = Resolve-Python
if ($python.Count -eq 2) {
  & $python[0] $python[1] $tool "roundtrip" "-i" $InputJson "-p" $OutputPrefix
} else {
  & $python[0] $tool "roundtrip" "-i" $InputJson "-p" $OutputPrefix
}
if ($LASTEXITCODE -ne 0) {
  throw "roundtrip failed with exit code $LASTEXITCODE"
}
