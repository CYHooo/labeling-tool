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
SetupIconFile={#MySourceRoot}\packaging\icon.ico
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
function InitializeSetup(): Boolean;
var
  Info: AnsiString;
begin
  Result := True;
  // Normal path: the client only downloads an app package whose asset name
  // carries this machine's runtime id, so this cannot fire. It guards the
  // user who downloaded the wrong file by hand. A machine with no
  // build-info.json is let through: there is no baseline to compare, and
  // refusing would block a legitimate repair install.
  if LoadStringFromFile(ExpandConstant('{autopf}\LM_LabelingTool\build-info.json'), Info) then
  begin
    if Pos('"{#MyRuntime}"', String(Info)) = 0 then
    begin
      MsgBox('이 업데이트는 현재 설치된 버전과 맞지 않습니다.' + #13#10 +
             '전체 설치 파일을 내려받아 주세요.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;
#endif

function WantsRestart(): Boolean;
begin
  // set by the in-app updater: relaunch after a silent install
  Result := WizardSilent and (Pos('/RESTARTAPP', GetCmdTail) > 0);
end;
