[CmdletBinding()]
param(
    [string]$Python = "py",
    [string]$InnoCompiler = "",
    [switch]$SkipDependencies,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildEnvironment = Join-Path $ProjectRoot ".venv-build"
$BuildPython = Join-Path $BuildEnvironment "Scripts\python.exe"
$Distribution = Join-Path $ProjectRoot "dist"

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Executable $($Arguments -join ' ')"
    }
}

if ($env:OS -ne "Windows_NT") {
    throw "Build this package on Windows x64; PyInstaller is not a Windows cross-compiler."
}
Push-Location $ProjectRoot
try {
    if (-not (Test-Path $BuildPython)) {
        if ($Python -eq "py") {
            Invoke-Checked $Python @("-3.12", "-m", "venv", $BuildEnvironment)
        } else {
            Invoke-Checked $Python @("-m", "venv", $BuildEnvironment)
        }
    }
    Invoke-Checked $BuildPython @("-c", "import sys,struct; assert sys.version_info[:2] == (3,12), 'Python 3.12 required'; assert struct.calcsize('P') == 8, '64-bit Python required'")
    if (-not $SkipDependencies) {
        Invoke-Checked $BuildPython @("-m", "pip", "install", "--timeout", "30", "--retries", "1", "-r", "requirements.txt", "-r", "requirements-midi.txt", "pyinstaller>=6.11,<7")
    }
    Invoke-Checked $BuildPython @("-m", "unittest", "discover", "-s", "tests", "-v")
    Invoke-Checked $BuildPython @("tools/download_model.py", "--face", "--pose")
    Invoke-Checked $BuildPython @("-m", "PyInstaller", "--noconfirm", "--clean", "packaging/HandControl.spec")

    # Windowed programs must be explicitly waited on from PowerShell.
    $FrozenExe = Join-Path $Distribution "HandControl\HandControl.exe"
    $SmokeReport = Join-Path $Distribution "self-test.json"
    $SmokeArguments = @("--self-test", "--report", "`"$SmokeReport`"")
    $SmokeProcess = Start-Process -FilePath $FrozenExe -ArgumentList $SmokeArguments -PassThru
    if (-not $SmokeProcess.WaitForExit(120000)) {
        $SmokeProcess.Kill()
        throw "Frozen executable self-test timed out after 120 seconds."
    }
    if ($SmokeProcess.ExitCode -ne 0 -or -not (Test-Path $SmokeReport)) {
        throw "Frozen executable self-test failed; see $SmokeReport when available."
    }
    # Reject a malformed report as well as a process failure.
    Get-Content $SmokeReport -Raw | ConvertFrom-Json | Out-Null

    $PortableZip = Join-Path $Distribution "HandControl-windows-x64.zip"
    Compress-Archive -Path (Join-Path $Distribution "HandControl") -DestinationPath $PortableZip -Force
    if (-not $SkipInstaller) {
        if (-not $InnoCompiler) {
            $DetectedCompiler = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
            if ($DetectedCompiler) {
                $InnoCompiler = $DetectedCompiler.Source
            } else {
                $InnoCompiler = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
            }
        }
        if (-not (Test-Path $InnoCompiler)) {
            throw "Inno Setup 6 compiler not found. Install it or pass -InnoCompiler <ISCC.exe>; use -SkipInstaller for portable ZIP only."
        }
        Invoke-Checked $InnoCompiler @("packaging/installer.iss")
        if (-not (Test-Path (Join-Path $Distribution "installer\HandControl-Setup.exe"))) {
            throw "Installer compiler completed without the expected installer artifact."
        }
    }
    Write-Host "Portable application: $PortableZip"
    if (-not $SkipInstaller) {
        Write-Host "Installer: $(Join-Path $Distribution 'installer\HandControl-Setup.exe')"
    }
} finally {
    Pop-Location
}
