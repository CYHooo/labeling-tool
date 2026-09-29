; Inno Setup script for LM_LabelingTool. Built by CI twice per release:
;   iscc /DMyLayer=full /DMyVersion=1.3.0 /DMyRuntime=r3f8a1c92 ^
;        /DMySource=<repo>\dist\LM_LabelingTool /DMySourceRoot=<repo> ^
;        /DMyOutDir=<repo>\out packaging\installer.iss
;   iscc /DMyLayer=app  ... /DMySource=<repo>\dist\app-layer ...
; The full package carries everything; the app package carries only our own
; code, for the common case where torch/CUDA did not change. See
; docs/superpowers/specs/2026-09-28-layered-distribution-design.md
; MySource/MyOutDir must be absolute: Inno resolves relative [Files] Source
; and OutputDir against this .iss file's own directory (packaging\), not the
; CI job's working directory.
; Per-user install by default, so updates need no administrator rights.
#ifndef MyLayer
  #define MyLayer "full"
#endif
#ifndef MyRuntime
  #define MyRuntime "r00000000"
#endif
#ifndef MySourceRoot
  #define MySourceRoot ".."
#endif
#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif
#ifndef MyVersionInfo
  #define MyVersionInfo "0.0.0"
#endif
#ifndef MySource
  #define MySource "dist\LM_LabelingTool"
#endif
#ifndef MyOutDir
  #define MyOutDir "out"
#endif

[Setup]
; One AppId for both layers: the app package must register as an UPGRADE of
; the existing install, not as a second program. This is the id the full
; variant has always used, so an existing v1.2.0 install upgrades in place
; and keeps config.json, data\ and checkpoint\.
AppId={{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02}
#define MyAppName "LM_LabelingTool"
DefaultDirName={autopf}\LM_LabelingTool
DefaultGroupName=LM_LabelingTool
AppName={#MyAppName}
AppVersion={#MyVersion}
AppPublisher=CYHooo
; Windows version resources must be numeric (x.y[.z[.w]]). Dev builds
; (MyVersion like "dev-a72cd7b") use MyVersionInfo="0.0.0" instead.
VersionInfoVersion={#MyVersionInfo}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no
DisableProgramGroupPage=yes
OutputDir={#MyOutDir}
; Must match checker.py's app_asset_name()/full_asset_name() exactly: the
; client finds its package by name alone. CI asserts both sides agree.
#if MyLayer == "app"
OutputBaseFilename=LM_LabelingTool-App-v{#MyVersion}-{#MyRuntime}
#else
OutputBaseFilename=LM_LabelingTool-Setup-v{#MyVersion}
#endif
UninstallDisplayIcon={app}\LM_LabelingTool.exe
SetupIconFile={#MySourceRoot}\labeling_tool\resources\icon.ico
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로 가기 만들기"; Flags: unchecked

[InstallDelete]
; ignoreversion below never removes files a newer build dropped, so without
; this, upgrades would accumulate stale _internal\ content forever.
; _internal\ holds no user data (config.json / data\ / checkpoint\ /
; classes.json all live directly under {app}), so this does not touch the
; uninstall-preserves-data guarantee.
;
; The app package must NOT clear _internal wholesale: it does not ship the
; ~1.4 GB runtime layer that lives there, so wiping it would leave the
; program unable to start. It clears only the two directories it replaces.
#if MyLayer == "app"
Type: filesandordirs; Name: "{app}\_internal\labeling_tool"
Type: filesandordirs; Name: "{app}\_internal\annotation_tool"
#else
Type: filesandordirs; Name: "{app}\_internal"
#endif

[Files]
; the whole PyInstaller onedir output; user data (config.json, data\,
; checkpoint\, classes.json) is created at runtime and never listed here,
; so uninstalling keeps it
Source: "{#MySource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\LM_LabelingTool.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\LM_LabelingTool.exe"; Tasks: desktopicon

[Run]
; interactive install: optional launch. Silent update (/RESTARTAPP): always.
Filename: "{app}\LM_LabelingTool.exe"; Description: "LM_LabelingTool 실행"; \
  Flags: nowait postinstall skipifsilent
Filename: "{app}\LM_LabelingTool.exe"; Flags: nowait runasoriginaluser; \
  Check: WantsRestart

[Code]
#if MyLayer == "app"
// Must equal [Setup]'s AppId. Built from literal parts because '{' starts a
// comment in Inno's Pascal and {#...} is a preprocessor directive -- an
// inline constant here silently produced a key with one brace too many,
// which made this guard find nothing at all (CI run 36518723697).
// labeling_tool/tests/test_installer_script.py asserts the two agree.
const
  APP_GUID = '{' + '9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02' + '}';

function InstalledDir(): String;
var
  Key: String;
begin
  // AppId is inherited from v1.2.0's full variant, which installed to
  // {autopf}\LabelingTool-full. Inno reinstalls into the directory it
  // RECORDED, so assuming today's default would make this guard dead on
  // exactly the machines it must protect. A custom /DIR does the same.
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + APP_GUID + '_is1';
  Result := '';
  if not RegQueryStringValue(HKCU, Key, 'InstallLocation', Result) then
    RegQueryStringValue(HKLM, Key, 'InstallLocation', Result);
  Result := RemoveBackslashUnlessRoot(Result);
end;

procedure Refuse(const Message: String);
begin
  // SuppressibleMsgBox, never MsgBox: /SUPPRESSMSGBOXES does not suppress a
  // [Code] MsgBox, so a silent install -- which is what the in-app updater
  // runs -- waits forever for a click nobody makes. One such call hung a CI
  // job for 96 minutes before it was killed.
  Log('app-layer guard refused: ' + Message);
  SuppressibleMsgBox(Message, mbError, MB_OK, IDOK);
end;

function InitializeSetup(): Boolean;
var
  Dir, Info: String;
  Raw: AnsiString;
begin
  // This package carries only our own code -- about 75 MB of a ~1.5 GB
  // install. Installed anywhere the matching runtime layer is not already
  // present, it produces a program that cannot start.
  Result := False;
  Dir := InstalledDir();
  if Dir = '' then
  begin
    Refuse('LM_LabelingTool 이 설치되어 있지 않습니다.' + #13#10 +
           '이 파일은 업데이트 전용입니다. 전체 설치 파일을 내려받아 주세요.');
    exit;
  end;
  Info := Dir + '\build-info.json';
  if not LoadStringFromFile(Info, Raw) then
  begin
    // No build-info.json means either no install or a damaged one. Both are
    // broken targets for a partial package.
    Refuse('설치 정보를 읽을 수 없습니다: ' + Info + #13#10 +
           '전체 설치 파일을 내려받아 주세요.');
    exit;
  end;
  if (Pos('"runtime":"{#MyRuntime}"', String(Raw)) = 0) and
     (Pos('"runtime": "{#MyRuntime}"', String(Raw)) = 0) then
  begin
    Refuse('이 업데이트는 현재 설치된 버전과 맞지 않습니다.' + #13#10 +
           '전체 설치 파일을 내려받아 주세요.');
    exit;
  end;
  Result := True;
end;
#endif

function WantsRestart(): Boolean;
begin
  // set by the in-app updater: relaunch after a silent install
  Result := WizardSilent and (Pos('/RESTARTAPP', GetCmdTail) > 0);
end;
