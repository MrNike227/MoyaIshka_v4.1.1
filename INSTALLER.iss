; Необязательный установщик Inno Setup.
; Сначала запустите BUILD_EXE.bat, затем откройте этот файл в Inno Setup Compiler.

[Setup]
AppId={{C6DBA092-A00B-4E45-9C02-67B8D543A2A1}
AppName=ISH
AppVersion=4.3.1
AppPublisher=ISH
DisableProgramGroupPage=yes
DefaultDirName={localappdata}\Programs\ISH_Container\App
UsePreviousAppDir=no
UninstallFilesDir={app}\..\Uninstall
DefaultGroupName=ISH
OutputDir=installer_output
OutputBaseFilename=ISH_Setup
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\ISH.exe
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительные значки:"; Flags: unchecked

[Dirs]
; Keep self-improvement data outside App so folder updates never delete it.
Name: "{app}\..\Updates"; Flags: uninsneveruninstall
; Keep the uninstaller outside the folder replaced by the onedir updater.
Name: "{app}\..\Uninstall"; Flags: uninsneveruninstall

[Files]
Source: "dist\ISH\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "licenses\GPL-3.0.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion

Source: "TEST_WINDOWS10.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ISH"; Filename: "{app}\ISH.exe"
Name: "{autodesktop}\ISH"; Filename: "{app}\ISH.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ISH.exe"; Description: "Запустить ISH"; Flags: postinstall nowait skipifsilent
