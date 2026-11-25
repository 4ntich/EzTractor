; Instalador do EzTractor para Windows (Inno Setup 6).
; Compilar:  iscc /DMyAppVersion=0.5.0 packaging\windows\installer.iss
; Requer a pasta dist\EzTractor gerada pelo PyInstaller (eztractor.spec).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{7C3AED11-E27A-4C70-9A11-5EB1A3F00D16}
AppName=EzTractor
AppVersion={#MyAppVersion}
AppPublisher=EzTractor
AppPublisherURL=https://github.com/4ntich/EzTractor
DefaultDirName={localappdata}\Programs\EzTractor
DefaultGroupName=EzTractor
DisableProgramGroupPage=yes
; instala só para o usuário atual: não pede senha de administrador
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=EzTractor-Setup-{#MyAppVersion}
SetupIconFile=eztractor.ico
UninstallDisplayIcon={app}\EzTractor.exe
UninstallDisplayName=EzTractor
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\..\dist\EzTractor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\EzTractor"; Filename: "{app}\EzTractor.exe"
Name: "{autodesktop}\EzTractor"; Filename: "{app}\EzTractor.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EzTractor.exe"; Description: "Abrir o EzTractor agora"; Flags: nowait postinstall skipifsilent

; Os vídeos, projetos e configurações ficam em %LOCALAPPDATA%\EzTractor e NÃO são apagados ao desinstalar.
