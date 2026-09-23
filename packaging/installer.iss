; Inno Setup script for LabelingTool. Built by CI:
;   iscc /DMyVariant=lite /DMyVersion=1.0.1 /DMySource=dist\LabelingTool /DMyOutDir=out packaging\installer.iss
; Per-user install by default, so updates need no administrator rights.
#ifndef MyVariant
  #define MyVariant "lite"
#endif
#ifndef MyVersion
  #define MyVersion "0.0.0"
#endif
#ifndef MySource
  #define MySource "dist\LabelingTool"
#endif
#ifndef MyOutDir
  #define MyOutDir "out"
#endif

[Setup]
; distinct AppId per variant: lite and full can coexist
#if MyVariant == "full"
AppId={{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02}
AppName=LabelingTool (Few-shot)
DefaultDirName={autopf}\LabelingTool-full
DefaultGroupName=LabelingTool (Few-shot)
#else
AppId={{9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F01}
AppName=LabelingTool
DefaultDirName={autopf}\LabelingTool
DefaultGroupName=LabelingTool
#endif
AppVersion={#MyVersion}
AppPublisher=CYHooo
VersionInfoVersion={#MyVersion}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no
DisableProgramGroupPage=yes
OutputDir={#MyOutDir}
OutputBaseFilename=LabelingTool-{#MyVariant}-Setup-v{#MyVersion}
UninstallDisplayIcon={app}\LabelingTool.exe
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로 가기 만들기"; Flags: unchecked

[Files]
; the whole PyInstaller onedir output; user data (config.json, data\,
; checkpoint\, classes.json) is created at runtime and never listed here,
; so uninstalling keeps it
Source: "{#MySource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LabelingTool"; Filename: "{app}\LabelingTool.exe"
Name: "{autodesktop}\LabelingTool"; Filename: "{app}\LabelingTool.exe"; Tasks: desktopicon

[Run]
; interactive install: optional launch. Silent update (/RESTARTAPP): always.
Filename: "{app}\LabelingTool.exe"; Description: "LabelingTool 실행"; \
  Flags: nowait postinstall skipifsilent
Filename: "{app}\LabelingTool.exe"; Flags: nowait runasoriginaluser; \
  Check: WantsRestart

[Code]
function WantsRestart(): Boolean;
begin
  // set by the in-app updater: relaunch after a silent install
  Result := WizardSilent and (Pos('/RESTARTAPP', GetCmdTail) > 0);
end;
