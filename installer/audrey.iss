#ifndef AppSource
  #define AppSource "..\installer\_staging\app"
#endif
#ifndef PythonEmbedZip
  #define PythonEmbedZip "..\installer\python-embed\python-embed.zip"
#endif
#ifndef GetPipPy
  #define GetPipPy "..\installer\python-embed\get-pip.py"
#endif
#ifndef OllamaInstaller
  #define OllamaInstaller "..\installer\vendor\OllamaSetup.exe"
#endif

[Setup]
AppId={{F39B4498-0A35-431A-A756-D5A2899F40F2}
AppName=AUDREY
AppVersion=1.0.0
AppPublisher=Sentra Artificial Intelligence
DefaultDirName={localappdata}\AUDREY
DefaultGroupName=AUDREY
OutputDir=..\dist
OutputBaseFilename=AUDREY-SETUP
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
SetupIconFile=assets\audrey.ico
UninstallDisplayIcon={app}\AUDREY.bat

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#PythonEmbedZip}"; DestDir: "{app}\bootstrap\python-embed"; DestName: "python-embed.zip"; Flags: ignoreversion
Source: "{#GetPipPy}"; DestDir: "{app}\bootstrap\python-embed"; Flags: ignoreversion
Source: "assets\audrey.ico"; DestDir: "{app}\bootstrap\assets"; Flags: ignoreversion
Source: "assets\classy.png"; DestDir: "{app}\bootstrap\assets"; Flags: ignoreversion
Source: "build-installer.ps1"; DestDir: "{app}\bootstrap"; Flags: ignoreversion
Source: "post_install.ps1"; DestDir: "{app}\bootstrap"; Flags: ignoreversion
Source: "first_run.ps1"; DestDir: "{app}\bootstrap"; Flags: ignoreversion
Source: "ensure_ollama.ps1"; DestDir: "{app}\bootstrap"; Flags: ignoreversion
Source: "ensure_model.ps1"; DestDir: "{app}\bootstrap"; Flags: ignoreversion
Source: "wheelhouse\*"; DestDir: "{app}\bootstrap\wheelhouse"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#OllamaInstaller}"; DestDir: "{app}\bootstrap\vendor"; DestName: "OllamaSetup.exe"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autodesktop}\AUDREY"; Filename: "{app}\AUDREY.bat"; WorkingDir: "{app}"; IconFilename: "{app}\bootstrap\assets\audrey.ico"
Name: "{autodesktop}\AUDREY Diagnose"; Filename: "{app}\diagnose-audrey.bat"; WorkingDir: "{app}"; IconFilename: "{app}\bootstrap\assets\audrey.ico"
Name: "{group}\AUDREY"; Filename: "{app}\AUDREY.bat"; WorkingDir: "{app}"; IconFilename: "{app}\bootstrap\assets\audrey.ico"
Name: "{group}\AUDREY Diagnose"; Filename: "{app}\diagnose-audrey.bat"; WorkingDir: "{app}"; IconFilename: "{app}\bootstrap\assets\audrey.ico"

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\bootstrap\post_install.ps1"" -InstallRoot ""{app}"""; Flags: waituntilterminated runhidden; StatusMsg: "Menyiapkan runtime AUDREY..."
Filename: "{app}\AUDREY.bat"; Description: "Launch AUDREY"; Flags: nowait postinstall skipifsilent
