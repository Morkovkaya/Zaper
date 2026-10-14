#define Payload "..\build\payload"
[Setup]
AppId={code:InstallerAppId}
AppName=Zapret 2 Manager
AppVersion=3.6.3
AppPublisher=Zapret 2 Manager Community
DefaultDirName={commonappdata}\zapret2
DisableDirPage=yes
UsePreviousAppDir=no
UsePreviousLanguage=no
UsePreviousGroup=no
UsePreviousTasks=no
UsePreviousUserInfo=no
UsePreviousSetupType=no
DefaultGroupName=Zapret 2 Manager
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=Zapret2Manager-Setup-3.6.3-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\app\Zapret2Manager.exe
UninstallFilesDir={app}\uninstall
InfoBeforeFile=install-info.txt
SetupLogging=yes
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"
Name: "service"; Description: "Установить и включить службу zapret 2 с автозапуском Windows"
[Files]
Source: "{#Payload}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Payload}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "app\*,licenses\*,lua\*,http3\*,windivert.filter\*,winws2.exe,cygwin1.dll,WinDivert.dll,WinDivert64.sys,runtime-sha256.json,files\faceit_legacy_udp.bin"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall
Source: "{#Payload}\winws2.exe"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall; Check: RuntimeDifferent('winws2.exe', 'EB9807972C15F05A00416B0549D766A71C9186F8101D406E3CC6C16278164D9E')
Source: "{#Payload}\cygwin1.dll"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall; Check: RuntimeDifferent('cygwin1.dll', '103104A52E5293CE418944725DF19E2BF81AD9269B9A120D71D39028E821499B')
Source: "{#Payload}\WinDivert.dll"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall; Check: RuntimeDifferent('WinDivert.dll', '16ABD6A029E65557C6A309BEA7B13BF81FFF4E193567582E1CDDBF6719F323E0')
Source: "{#Payload}\WinDivert64.sys"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall; Check: RuntimeDifferent('WinDivert64.sys', '8DA085332782708D8767BCACE5327A6EC7283C17CFB85E40B03CD2323A90DDC2')
Source: "{#Payload}\runtime-sha256.json"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall
Source: "{#Payload}\files\faceit_legacy_udp.bin"; DestDir: "{app}\files"; Flags: ignoreversion uninsneveruninstall
Source: "{#Payload}\lua\*"; DestDir: "{app}\lua"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "{#Payload}\http3\*"; DestDir: "{app}\http3"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "{#Payload}\windivert.filter\*"; DestDir: "{app}\windivert.filter"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "{#Payload}\app\Zapret2Manager.exe"; DestName: "SetupRepair.exe"; Flags: dontcopy
[Icons]
Name: "{group}\Zapret 2 Manager"; Filename: "{app}\app\Zapret2Manager.exe"; WorkingDir: "{app}\app"; Check: Not TestMode
Name: "{group}\Удалить Zapret 2 Manager"; Filename: "{uninstallexe}"; Check: Not TestMode
Name: "{autodesktop}\Управление zapret 2"; Filename: "{app}\app\Zapret2Manager.exe"; WorkingDir: "{app}\app"; Tasks: desktopicon; Check: Not TestMode
[Run]
Filename: "{app}\app\Zapret2Manager.exe"; Description: "Открыть Zapret 2 Manager"; Flags: postinstall nowait skipifsilent runascurrentuser; Check: Not TestMode
[Code]
function InstallerAppId(Param: String): String;
begin
 if ExpandConstant('{param:TESTMODE|0}') = '1' then
  Result := 'Zapret2ManagerTest-' + GetMD5OfString(ExpandConstant('{param:DIR|isolated}'))
 else Result := '{835F617D-7E48-4C26-B268-E5E20F504AB2}';
end;
function TestMode: Boolean;
begin Result := ExpandConstant('{param:TESTMODE|0}') = '1'; end;
function RuntimeDifferent(Name, ExpectedHash: String): Boolean;
begin
 Result := True;
 if FileExists(ExpandConstant('{app}\') + Name) then begin
  try Result := CompareText(GetSHA256OfFile(ExpandConstant('{app}\') + Name), ExpectedHash) <> 0;
  except Result := True; end;
 end;
end;
function InitializeSetup: Boolean;
var Release: Cardinal;
begin
 Result := RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full', 'Release', Release) and (Release >= 528040);
 if not Result then MsgBox('Нужен .NET Framework 4.8. Установите его с сайта Microsoft и повторите установку.', mbError, MB_OK);
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
 Result := '';
 ExtractTemporaryFile('SetupRepair.exe');
 if not Exec(ExpandConstant('{tmp}\SetupRepair.exe'), '--prepare-target "' + ExpandConstant('{app}') + '"', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
  Result := 'Не удалось подготовить службы к обновлению. См. package-error.txt в папке установки; завершите активный автоподбор.';
end;
procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer; Args: String;
begin
 if CurStep = ssPostInstall then begin
  Args := '--configure-package';
  if WizardIsTaskSelected('service') and not TestMode then Args := Args + ' --install-service';
  if not Exec(ExpandConstant('{app}\app\Zapret2Manager.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
   RaiseException('Не удалось проверить конфигурацию zapret 2. См. package-error.txt в папке установки.');
 end;
end;
function InitializeUninstall: Boolean;
var Code: Integer;
begin
 Result := Exec(ExpandConstant('{app}\app\Zapret2Manager.exe'), '--uninstall-package', '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
 if not Result then MsgBox('Не удалось остановить службу. Закройте приложение и завершите автоподбор, затем повторите удаление.', mbError, MB_OK);
end;





