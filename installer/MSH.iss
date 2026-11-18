#define MyAppName "MSH"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.4"
#endif
#ifndef MyBuildDir
  #define MyBuildDir "..\dist\cpu\MSH"
#endif
#ifndef MyBuildSuffix
  #define MyBuildSuffix "CPU"
#endif
#ifndef MyCompression
  #define MyCompression "lzma2/max"
#endif
#define MyAppPublisher "Microscope Scanner Helper"
#define MyAppExeName "MSH.exe"

[Setup]
AppId={{EDC6AF82-E6F1-48E4-92B1-94342E4B8EA7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MSH
DefaultGroupName=MSH
DisableProgramGroupPage=yes
OutputDir=..\dist\release\v{#MyAppVersion}
OutputBaseFilename=MSH_Setup_v{#MyAppVersion}_{#MyBuildSuffix}
SetupIconFile=..\assets\msh-pixel-icon.ico
InfoBeforeFile=PREREQUISITES.txt
Compression={#MyCompression}
LZMANumBlockThreads=4
LZMABlockSize=131072
LZMAUseSeparateProcess=yes
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64os
ArchitecturesAllowed=x64os
MinVersion=10.0
AppMutex=Local\MSH_Hardware_GUI_Launcher
CloseApplications=no
RestartApplications=no
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\MSH"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\MSH"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch MSH"; Flags: nowait postinstall skipifsilent; Check: AllowLaunch
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runasoriginaluser; Check: AutoLaunch

[Code]
function AllowLaunch: Boolean;
begin
  Result := (ExpandConstant('{param:MSHNOLAUNCH|0}') = '0') and
    (ExpandConstant('{param:MSHAUTORESTART|0}') <> '1');
end;

function AutoLaunch: Boolean;
begin
  Result := (ExpandConstant('{param:MSHNOLAUNCH|0}') = '0') and
    (ExpandConstant('{param:MSHAUTORESTART|0}') = '1');
end;
