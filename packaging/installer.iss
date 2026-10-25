; Compile after packaging/HandControl.spec has produced dist/HandControl.
#define AppName "Hand Control Lab"
#define AppVersion "0.3.1"
#define ProjectRoot AddBackslash(SourcePath) + ".."

[Setup]
AppId={{0CB4028C-435F-4D8D-B30F-C94A2D9B9FB2}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Hand Control contributors
DefaultDirName={localappdata}\Programs\HandControl
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
SourceDir={#ProjectRoot}
OutputDir={#ProjectRoot}\dist\installer
OutputBaseFilename=HandControl-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayIcon={app}\HandControl.exe
LicenseFile={#ProjectRoot}\LICENSE
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\HandControl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\HandControl.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\HandControl.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\HandControl.exe"; Description: "Open {#AppName}"; Flags: nowait postinstall skipifsilent

; No [UninstallDelete] entry: calibration, drawings, recordings and logs in
; the separate per-user data directory must survive an uninstall.
