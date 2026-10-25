# Windows application and installer

The Windows package is designed to open a Tkinter launcher when you double-click `HandControl.exe`. Installed users do not need Python or batch files. The build includes the hand, face and pose models, so normal model startup does not need a download. Experiments requiring optional IR or WiLoR libraries remain optional; they are not bundled or enabled by this installer. Live MIDI support is bundled, but a suitable MIDI destination/virtual port must still exist on Windows.

**The installer configuration has not been built or run on Windows in this Linux workspace.** A successful Windows build and frozen self-test are prerequisites for distributing the resulting artifacts as verified. Camera tracking, GUI layout, MIDI routing and physical interaction still require a real Windows trial. This project provides no code-signing certificate; unsigned Windows downloads may display SmartScreen or reputation warnings.

## Install a built artifact

1. Obtain `HandControl-Setup.exe` from a successful Windows build artifact, then run it on Windows 11 x64.
2. The per-user installer uses `%LOCALAPPDATA%\Programs\HandControl`; administrator access is not required.
3. Open **Hand Control Lab** from the Start menu or the optional desktop shortcut.
4. Use a sandbox/preview before enabling desktop mouse output. Camera access remains subject to Windows privacy settings and the physical camera shutter.

Uninstall through Windows Settings → Apps → Installed apps. The installer removes its installed files and shortcuts; it deliberately does not delete separately stored user calibration, drawings, recordings or logs. Do not store personal outputs manually in the application installation folder.

For a portable version, extract **the entire** `HandControl-windows-x64.zip`, then launch `HandControl\HandControl.exe`. Keep the `_internal` folder next to the executable. Copying only the EXE will not work.

## Build locally

Required: Windows x64, Python 3.12 x64 with the Python launcher, Internet access for dependencies/models, and [Inno Setup 6](https://jrsoftware.org/isdl.php) for the installer. Obtain build tools through their official distributions. No automatic driver or security-setting changes occur.

From a PowerShell session in the project folder:

```powershell
./packaging/build-windows.ps1
```

If local PowerShell policy blocks scripts, follow your device's policy or run the commands in the script manually; this project does not change your execution policy. To select an explicit Python interpreter or Inno compiler:

```powershell
./packaging/build-windows.ps1 -Python 'C:\Path\To\Python312\python.exe' -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

The script creates `.venv-build`, installs the base and MIDI requirements plus PyInstaller `>=6.11,<7`, runs the unit tests, downloads all three versioned MediaPipe models, builds a windowed onedir executable and runs a headless frozen smoke test. Direct application dependencies are pinned/bounded in the requirements; the complete transitive build environment is not a reproducible lockfile. To reuse an existing environment without package installation, pass `-SkipDependencies`. `-SkipInstaller` creates only the portable ZIP.

Outputs:

- `dist/HandControl/HandControl.exe` with its `_internal` support directory.
- `dist/HandControl-windows-x64.zip` — complete portable application.
- `dist/installer/HandControl-Setup.exe` — per-user installer.
- `dist/self-test.json` — frozen application smoke-test report.

Resources are bundled under `sys._MEIPASS/models` in the frozen app. The application must write mutable settings/logs to a separate writable user-data directory, never `_internal` or the installation directory. Worker processes must launch the same frozen executable with `--worker` and log their output there.

## Build in GitHub Actions

The `Build Windows application` workflow supports manual `workflow_dispatch` and source-path-filtered pushes. It uses Windows runners and Python 3.12 x64, executes the same build script, and uploads the installer, portable ZIP and smoke report. Publishing this repository or triggering a remote workflow has not been done here. Download the `HandControl-windows-x64` artifact only after a successful run.

## Frozen smoke test contract

```powershell
Start-Process -Wait -FilePath .\dist\HandControl\HandControl.exe -ArgumentList '--self-test', '--report', 'self-test.json'
```

The entry point must process `--self-test` before creating Tk windows or opening a camera. It must return zero on success and write valid JSON to the requested report path. The build waits up to 120 seconds, requires a zero exit code and validates that report as JSON. This verifies packaging/resource/import behavior; it does not prove webcam accuracy or successful Windows input injection.
