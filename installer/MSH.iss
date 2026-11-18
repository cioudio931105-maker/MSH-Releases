#define MyAppName "MSH"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.1"
#endif
#ifndef MyBuildDir
  #define MyBuildDir "..\dist\cpu\MSH"
#endif
#ifndef MyBuildSuffix
  #define MyBuildSuffix "CPU"
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
OutputDir=..\dist\release
OutputBaseFilename=MSH_Setup_v{#MyAppVersion}_{#MyBuildSuffix}
SetupIconFile=..\assets\msh-pixel-icon.ico
InfoBeforeFile=PREREQUISITES.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\MSH"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\MSH"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch MSH"; Flags: nowait postinstall skipifsilent
