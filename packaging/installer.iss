; Inno Setup script for LM_LabelingTool. Built by CI once per release:
;   iscc /DMyVersion=1.3.0 ^
;        /DMySource=<repo>\dist\LM_LabelingTool /DMySourceRoot=<repo> ^
;        /DMyOutDir=<repo>\out packaging\installer.iss
; One installer carries everything; incremental updates are zips applied in
; place by labeling_tool/update/patch.py. See
; docs/superpowers/specs/2026-10-02-single-package-release-design.md
; MySource/MyOutDir must be absolute: Inno resolves relative [Files] Source
; and OutputDir against this .iss file's own directory (packaging\), not the
; CI job's working directory.
; Per-user install by default, so updates need no administrator rights.
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
#ifndef MyTestInstall
AppId={{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02}
#define MyAppName "LM_LabelingTool"
#else
; /DMyTestInstall: packaging/ci/local-build.ps1's smoke test only. Its own
; AppId and Start menu entry, so installing, upgrading and uninstalling on a
; workstation never touches the copy that is installed there for real.
AppId={{73FDC7BA-1CC5-4842-80BD-078ED75FD1A6}
#define MyAppName "LM_LabelingTool-test"
#endif
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AppName={#MyAppName}
AppVersion={#MyVersion}
AppPublisher=CYHooo
; Windows version resources must be numeric (x.y[.z[.w]]). Dev builds
; (MyVersion like "dev-a72cd7b") use MyVersionInfo="0.0.0" instead.
VersionInfoVersion={#MyVersionInfo}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Compression is over half of a CI run: lzma2/max with solid compression
; takes ~12 of ~22 minutes to squeeze 4 GB into 1.5 GB. Release builds pay
; that for the download size users actually see; verification builds do not
; need to, so CI passes /DMyFast=1 when it is not building a tag.
#ifdef MyFast
Compression=lzma2/fast
SolidCompression=no
#else
Compression=lzma2/max
SolidCompression=yes
; Four compression threads, one per core of a GitHub runner. Measured on
; the v1.4 full installer: 645 s -> 200 s, 1522.0 MB -> 1538.5 MB (+1.1%).
LZMANumBlockThreads=4
LZMAUseSeparateProcess=yes
#endif
CloseApplications=force
RestartApplications=no
DisableProgramGroupPage=yes
OutputDir={#MyOutDir}
; Must match checker.full_asset_name() exactly: the client finds its
; package by name alone. CI asserts both sides agree.
OutputBaseFilename=LM_LabelingTool-Setup-v{#MyVersion}
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
Type: filesandordirs; Name: "{app}\_internal"
; leftovers of an interrupted zip update (labeling_tool/update/patch.py)
Type: filesandordirs; Name: "{app}\.update-backup"
Type: filesandordirs; Name: "{app}\.update-staging"
Type: files;          Name: "{app}\.update-journal"

[UninstallDelete]
; zip updates (labeling_tool/update/patch.py) leave these beside the install
Type: filesandordirs; Name: "{app}\.update-backup"
Type: filesandordirs; Name: "{app}\.update-staging"
Type: files;          Name: "{app}\.update-journal"

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
function WantsRestart(): Boolean;
begin
  // set by the in-app updater: relaunch after a silent install
  Result := WizardSilent and (Pos('/RESTARTAPP', GetCmdTail) > 0);
end;
