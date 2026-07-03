#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "Maidie Desktop Pet"
#define MyAppPublisher "Maidie Desktop Pet"
#define MyAppExeName "Maidie.exe"

[Setup]
AppId={{DF6C28A8-C3FC-49A7-AB97-415B162A87C3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Maidie
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=Maidie-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
CloseApplications=yes
RestartApplications=no
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=maidie.ico

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
Source: "..\dist\Maidie\*"; DestDir: "{app}"; Excludes: "config\config.json,logs\*,memory\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\Maidie\config\config.json"; DestDir: "{app}\config"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\Maidie Desktop Pet"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Maidie Desktop Pet"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 Maidie Desktop Pet"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
