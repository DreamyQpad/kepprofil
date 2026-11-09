; Képprofil telepítő (Inno Setup 6). Fordítás: ISCC.exe telepito.iss
; Előfeltétel: build_installer\dist\Kepprofil\ kész (PyInstaller).

#define AppName "Képprofil"
#define AppVersion "2.2"
#define AppExe "Kepprofil.exe"
; az előző név ("Kijelző") telepítőjének AppId-ja: azt telepítés előtt eltávolítjuk
#define OldAppId "{B3F1C2A4-6D5E-4F7A-8C91-2E4D7A9B1C30}"

[Setup]
AppId={{7C2E9D41-5B8A-4E36-A1F0-93D6B4C8E512}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; felhasználói telepítés (nem kér rendszergazdát)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\out
OutputBaseFilename=Kepprofil-telepito
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UsePreviousAppDir=yes
CloseApplications=force

[Languages]
Name: "hu"; MessagesFile: "compiler:Languages\Hungarian.isl"

[Tasks]
Name: "desktopicon"; Description: "Asztali parancsikon létrehozása"; GroupDescription: "További parancsikonok:"
Name: "autostart"; Description: "Indítás a Windows-szal (a tálcán, ablak nélkül)"; GroupDescription: "Működés:"

[Files]
Source: "dist\Kepprofil\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--tray"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} indítása"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "KillKepprofil"

[Code]
var
  OldHadAutostart: Boolean;

function OldUninstallString(): String;
var
  key, s: String;
begin
  Result := '';
  key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#OldAppId}_is1';
  if RegQueryStringValue(HKCU, key, 'UninstallString', s) then
    Result := s
  else if RegQueryStringValue(HKLM, key, 'UninstallString', s) then
    Result := s;
end;

procedure InitializeWizard();
begin
  // ha az előző változatnál be volt kapcsolva az indítás a Windows-szal, itt is legyen bepipálva
  OldHadAutostart := FileExists(ExpandConstant('{userstartup}\Kijelző.lnk'));
  if OldHadAutostart then
    WizardSelectTasks('autostart');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  rc: Integer;
  u: String;
begin
  // futó (tálcás) példányok leállítása; az új indítás rendezi a kijelzőt
  Exec('taskkill.exe', '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, rc);
  // az előző ("Kijelző") változat eltávolítása; az adatai (presetek) megmaradnak, az új program átveszi őket
  u := OldUninstallString();
  if u <> '' then
  begin
    u := RemoveQuotes(u);
    Exec(u, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, rc);
  end;
  Result := '';
end;
