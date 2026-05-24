#define AppName      "Arkland Player"
#define AppVersion   "1.0.12"
#define AppPublisher "Arkland"
#define AppExeName   "ArklandPlayer.exe"
#define SourceDir    SourcePath + "\dist\ArklandPlayer"

[Setup]
AppId={{F3A2B1C4-9D7E-4F8A-B2C3-1A4D5E6F7890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#SourcePath}\dist
OutputBaseFilename=ArklandPlayer-Setup
SetupIconFile={#SourcePath}\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\{#AppExeName}";     DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\updater_agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*";       DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\_internal\img\logo_akl_player.png"
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\_internal\img\logo_akl_player.png"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
