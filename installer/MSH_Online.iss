; Build through scripts/build_online_installer.py. All downloads are pinned by hash.
#ifndef PayloadConfig
  #error PayloadConfig is required
#endif
#include PayloadConfig

[Setup]
AppId={{6E1C9D61-7027-49AC-9A66-AD3A18B473F5}
AppName=MSH Online Setup
AppVersion={#MyAppVersion}
AppPublisher=Microscope Scanner Helper
CreateAppDir=no
Uninstallable=no
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputName}
SetupIconFile=..\assets\msh-pixel-icon.ico
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
DisableDirPage=yes
DisableProgramGroupPage=yes
AppMutex=Local\MSH_Hardware_GUI_Launcher
CloseApplications=no
RestartApplications=no
InfoBeforeFile=PREREQUISITES.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Code]
var
  RuntimePage: TInputOptionWizardPage;
  BaslerPage: TInputOptionWizardPage;
  DownloadPage: TDownloadWizardPage;
  SelectedInstaller: String;
  PylonPresent, RebootNeeded: Boolean;

function HasNvidiaAdapter: Boolean;
var
  Locator, Services, Adapters: Variant;
begin
  Result := True; { If inventory fails, keep NVIDIA-first and allow manual CPU selection. }
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Services := Locator.ConnectServer('', 'root\CIMV2');
    Adapters := Services.ExecQuery('SELECT Name FROM Win32_VideoController WHERE Name LIKE ''%NVIDIA%''');
    Result := Adapters.Count > 0;
  except
    Log('GPU inventory unavailable; user can select CPU fallback.');
  end;
end;

function HasPylonProduct(Root: Integer): Boolean;
var
  Names: TArrayOfString;
  Index: Integer;
  DisplayName, BaseKey: String;
begin
  Result := False;
  BaseKey := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall';
  if RegGetSubkeyNames(Root, BaseKey, Names) then
    for Index := 0 to GetArrayLength(Names) - 1 do
      if RegQueryStringValue(Root, BaseKey + '\' + Names[Index], 'DisplayName', DisplayName) then
        if (Pos('basler', Lowercase(DisplayName)) > 0) and
           (Pos('pylon', Lowercase(DisplayName)) > 0) then
          Result := True;
end;

procedure InitializeWizard;
begin
  RuntimePage := CreateInputOptionPage(wpWelcome, 'MSH compute environment',
    'NVIDIA GPU preferred; CPU is the fallback.',
    'The selected package includes Python and its dependencies. GPU compatibility is tested when MSH starts. ' +
    'A CPU package cannot enable CUDA without installing the GPU package.', True, False);
  RuntimePage.Add('NVIDIA GPU package (requires a compatible NVIDIA GPU and driver)');
  RuntimePage.Add('CPU fallback package (slower; live scanning performance needs validation)');
  if HasNvidiaAdapter then RuntimePage.SelectedValueIndex := 0
  else RuntimePage.SelectedValueIndex := 1;
  PylonPresent := HasPylonProduct(HKLM64) or HasPylonProduct(HKLM32) or HasPylonProduct(HKCU);
  BaslerPage := CreateInputOptionPage(RuntimePage.ID, 'Basler USB camera',
    'Official USB prerequisites; existing installations are preserved.',
    'Installation records do not prove USB driver compatibility. The official installer may request ' +
    'administrator permission or a reboot. No camera, COM port or motor settings are changed by MSH Setup.', False, False);
#ifdef PylonUrl
  BaslerPage.Add('Install the reviewed official Basler runtime / USB prerequisites if absent');
  BaslerPage.Values[0] := not PylonPresent;
#else
  BaslerPage.Add('Open the official Basler download page after installing MSH');
  BaslerPage.Values[0] := not PylonPresent;
  BaslerPage.SubCaptionLabel.Caption := BaslerPage.SubCaptionLabel.Caption +
    ' This internal build has no approved Basler download pinned yet; automatic driver installation is unavailable.';
#endif
  if PylonPresent then BaslerPage.SubCaptionLabel.Caption := BaslerPage.SubCaptionLabel.Caption +
    ' Existing pylon software was found. Automatic replacement or upgrade is disabled.';
  DownloadPage := CreateDownloadPage('Downloading MSH',
    'HTTPS downloads are checked against the hashes embedded in this installer.', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID <> wpReady then exit;
#ifdef PylonUrl
  if PylonPresent and BaslerPage.Values[0] then begin
    MsgBox('Existing pylon installation is preserved. Uncheck the Basler option to continue. ' +
      'Use the MSH diagnostics and an authorized hardware session before changing existing drivers.', mbInformation, MB_OK);
    Result := False;
    exit;
  end;
#endif
  DownloadPage.Clear;
  if RuntimePage.SelectedValueIndex = 0 then begin
    SelectedInstaller := 'MSH_GPU_Setup.exe';
    DownloadPage.Add('{#GpuUrl}', SelectedInstaller, '{#GpuSha256}');
  end else begin
    SelectedInstaller := 'MSH_CPU_Setup.exe';
    DownloadPage.Add('{#CpuUrl}', SelectedInstaller, '{#CpuSha256}');
  end;
#ifdef PylonUrl
  if BaslerPage.Values[0] and not PylonPresent then
    DownloadPage.Add('{#PylonUrl}', 'Basler_Runtime_Setup.exe', '{#PylonSha256}');
#endif
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
    except
      if not DownloadPage.AbortedByUser then
        MsgBox('Download or checksum verification failed. The installed MSH version has not been changed. ' +
          'Check the network and repository access, then retry.' + #13#10 + GetExceptionMessage,
          mbError, MB_OK);
      Result := False;
    end;
  finally
    DownloadPage.Hide;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
  Arguments: String;
begin
  if CurStep <> ssInstall then exit;
#ifdef PylonUrl
  if BaslerPage.Values[0] and not PylonPresent then begin
    { Interactive official installer: user sees its EULA and chooses USB components.
      No allowupgrade/repair/uninstall switches and no silent EULA acceptance. }
    if not ShellExec('runas', ExpandConstant('{tmp}\Basler_Runtime_Setup.exe'), '', '',
        SW_SHOWNORMAL, ewWaitUntilTerminated, ExitCode) then
      RaiseException('Basler setup was not started; MSH installation cancelled.');
    if (ExitCode <> 0) and (ExitCode <> 3010) and (ExitCode <> 1641) then
      RaiseException('Basler setup failed or was cancelled. MSH installation cancelled.');
    RebootNeeded := (ExitCode = 3010) or (ExitCode = 1641);
  end;
#endif
  Arguments := '/NORESTART';
  if WizardSilent then Arguments := Arguments + ' /SILENT /SUPPRESSMSGBOXES /SP-';
  if ExpandConstant('{param:MSHAUTORESTART|0}') = '1' then
    Arguments := Arguments + ' /MSHAUTORESTART=1';
  if RebootNeeded then Arguments := Arguments + ' /MSHNOLAUNCH=1';
  if not Exec(ExpandConstant('{tmp}\') + SelectedInstaller, Arguments, '',
      SW_SHOWNORMAL, ewWaitUntilTerminated, ExitCode) then
    RaiseException('MSH package installer could not be started.');
  if (ExitCode <> 0) and (ExitCode <> 3010) then
    RaiseException('MSH package installation failed or was cancelled (code ' + IntToStr(ExitCode) + ').');
  RebootNeeded := RebootNeeded or (ExitCode = 3010);
#ifndef PylonUrl
  if BaslerPage.Values[0] and not WizardSilent then
    ShellExec('open', 'https://www.baslerweb.com/en/downloads/software/', '', '', SW_SHOWNORMAL,
      ewNoWait, ExitCode);
#endif
end;

function NeedRestart: Boolean;
begin
  Result := RebootNeeded;
end;
