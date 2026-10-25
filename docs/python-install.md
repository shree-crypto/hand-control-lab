# Install as a Python application

The project is an installable native Python package named **hand-control-lab**, version **0.3.1**. It has not been published to PyPI. Use the supplied source folder or wheel; `pip install hand-control-lab` is not an advertised installation route.

Windows 11 with **Python 3.12 x64** is the supported target for this package version. The Python constraint is `>=3.12,<3.13`; other Python versions are not silently accepted. Hand tracking, camera behavior, MIDI ports and device latency still require a trial on your own laptop.

## Install the source folder

Open PowerShell in the extracted project folder containing `pyproject.toml`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[midi]"
.\.venv\Scripts\hand-control.exe
```

The `midi` extra adds optional live MIDI dependencies. Omit it to use camera playgrounds and MIDI-file recording without live MIDI transport:

```powershell
.\.venv\Scripts\python.exe -m pip install .
```

If you prefer installing into your existing Python 3.12 environment rather than a project virtual environment, the equivalent is:

```powershell
py -3.12 -m pip install ".[midi]"
hand-control
```

Installation needs internet access for dependencies unless their wheels are already available locally. These pinned dependencies have prebuilt Windows x64 wheels for Python 3.12, so the normal wheel-based installation does not require a C++ compiler. If pip starts building a dependency from source, check the Python version, architecture, package index and wheel availability rather than assuming a compiler is required.

## Install a supplied wheel

From the folder containing the release wheel:

```powershell
py -3.12 -m pip install ".\hand_control_lab-0.3.1-py3-none-any.whl[midi]"
hand-control
```

The application wheel is Python source and works with platform-specific dependencies; the `py3-none-any` wheel tag does not promise that Windows desktop control, native MIDI backends or the supported Python range are portable to every system.

## Launchers

| Command | Behavior |
| --- | --- |
| `hand-control` | Open the desktop launcher; explicit mode arguments such as `hand-control drums` run that mode |
| `hand-control-gui` | Open the same desktop launcher without a console window on Windows |
| `hand-control-cli` | Preserve the command-line interface; no arguments starts the existing preview |
| `py -3.12 -m gesture_control` | Existing CLI module, unchanged by installation metadata |

For example:

```powershell
hand-control --version
hand-control --self-test
hand-control --download-models
hand-control drums --list-ports
hand-control drums --port "Your loopMIDI Port"
```

Model downloads are separate from installation and require internet access once. Models are not bundled into the wheel or source distribution. Runtime uses the application's writable model/cache location, not a write into the installed package directory. Use the desktop launcher's setup/status instructions to confirm the models are present.

On Windows, launcher settings, logs and downloaded models live under `%LOCALAPPDATA%\HandControl`. Existing calibration profiles remain in their per-user locations or in files you select. Source and frozen installs also recognize bundled/source `models` when present. The Windows native build bundles all three models; the Python wheel downloads them from the launcher when you choose **Download models**.

In Settings you can choose the calibration hand and the primary/secondary contact fingers without using command-line options. For example, select Left/ring/pinky or Right/index/middle before starting **Calibrate desktop gestures**. A nonempty pointer-hand profile path is also the output location for that calibration mode. Test saved settings in preview first.

Live MIDI opens an **existing output port**. On Windows, configure a loopMIDI port and connect that port in your DAW. Installing the `midi` extra does not create a virtual MIDI device or install a synthesizer, and selecting an output does not establish any particular end-to-end audio latency.

## If a launcher command is not found

For a project virtual environment, invoke its executable directly as shown above. For a regular Python installation, its Scripts directory may not be on `PATH`. You can start the desktop entry module directly:

```powershell
py -3.12 -m gesture_control.desktop_entry
```

Use the same Python installation for installation and launching. If you installed into `.venv`, use `.\.venv\Scripts\python.exe -m gesture_control.desktop_entry` rather than the global `py` command.

## Native executable builds are separate

The optional `build` extra installs PyInstaller for a developer who wants to build a Windows executable:

```powershell
py -3.12 -m pip install ".[build,midi]"
```

This extra does not build or install a standalone `.exe` by itself. Follow the release/build instructions for the supplied native packaging scripts. A Python package installation and a standalone Windows executable are two distribution choices for the same application; no npm runtime is required.

Documentation and the project license are included under the installation's `share/doc/hand-control-lab` data directory as well as the source distribution. External models, camera SDKs, IR access, NPU backends and their licenses remain separate optional concerns.
