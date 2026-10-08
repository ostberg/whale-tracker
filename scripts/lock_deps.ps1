<#
.SYNOPSIS
    Regenerate the two dependency locks (hash-pinned, versions held) from pyproject.toml.

.DESCRIPTION
    The locks are the only thing production and CI install from (AGENTS.md, "Supply chain"; W-022). This
    script is the recipe, copied from the Tamale repo's scripts/lock_deps.ps1 so both projects lock the same
    way.

      requirements-runtime.lock   core dependencies         what the container image installs (--require-hashes)
      requirements-dev.lock       core + [dev]              what CI and developers install (--require-hashes)

    Both carry --generate-hashes. The dev lock also carries --allow-unsafe, so pip and setuptools are pinned
    with hashes too, and is constrained to the runtime lock, so CI tests exactly what production runs.

    Versions do not move. Without -Upgrade, pip-compile keeps every existing pin. Bumping is deliberate:
    .\scripts\lock_deps.ps1 -Upgrade <package>, then review the diff and commit it.

    Run from the repo venv (pip-tools is in the [dev] extra). The very first lock was produced with the
    Tamale repo venv's pinned pip-tools, so nothing unpinned was installed to bootstrap.

.PARAMETER Upgrade
    Package name(s) allowed to move (pip-compile --upgrade-package). Omit to hold every pin.

.PARAMETER Python
    The interpreter that has pip-tools. Defaults to this repo's .venv.
#>
[CmdletBinding()]
param(
    [string[]]$Upgrade = @(),
    [string]$Python = ''
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    $py = if ($Python) { $Python } else { Join-Path $repo '.venv\Scripts\python.exe' }
    if (-not (Test-Path $py)) { throw "no interpreter at $py (create the venv first; AGENTS.md, Environment)" }

    # --quiet: pip-compile otherwise echoes the whole lock to stderr, which Windows PowerShell 5.1 renders
    # as a wall of red ErrorRecords. The file on disk is the output.
    $common = @('--quiet', '--generate-hashes', '--no-strip-extras', '--resolver=backtracking')
    foreach ($p in $Upgrade) { $common += "--upgrade-package=$p" }

    Write-Host "runtime lock ..." -ForegroundColor Cyan
    & $py -m piptools compile @common --output-file=requirements-runtime.lock pyproject.toml 2>&1 |
        ForEach-Object { "$_" } | Where-Object { $_ -notmatch 'strip-extras' }
    if ($LASTEXITCODE -ne 0) { throw "runtime lock failed (exit $LASTEXITCODE)" }

    Write-Host "dev lock (--allow-unsafe; constrained to the runtime lock) ..." -ForegroundColor Cyan
    & $py -m piptools compile @common --allow-unsafe --constraint requirements-runtime.lock --extra=dev `
        --output-file=requirements-dev.lock pyproject.toml 2>&1 |
        ForEach-Object { "$_" } | Where-Object { $_ -notmatch 'strip-extras' }
    if ($LASTEXITCODE -ne 0) { throw "dev lock failed (exit $LASTEXITCODE)" }

    foreach ($f in 'requirements-runtime.lock', 'requirements-dev.lock') {
        if (Select-String -Path $f -Pattern 'WARNING: The following packages were not pinned' -Quiet) {
            throw "$f contains packages pip would reject under --require-hashes; see its # WARNING block"
        }
    }
    Write-Host "Locks regenerated. Review git diff, then commit." -ForegroundColor Green
    exit 0
}
finally { Pop-Location }
