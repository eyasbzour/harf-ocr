; Harf OCR installer (Inno Setup 6). Built by the GitHub workflow after desktop\build.ps1:
;   iscc /DAppVersion=1.0.0 /DHeavyVersion=1 desktop\installer.iss      ->  build\out\HarfOCR-Setup-1.0.0.exe
; Per-user install (no administrator rights), so updates can run silently. The optional readers (Nuqta and
; EasyOCR, about 2 GB) are not inside the setup file: when chosen, they are downloaded from the same release.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef HeavyVersion
  #define HeavyVersion "1"
#endif
#define Repo "eyasbzour/harf-ocr"
#define Release "https://github.com/" + Repo + "/releases/download/v" + AppVersion

[Setup]
AppId={{6F2B8C4E-1D7A-4E59-9C1B-3A5E7D2F8B90}
; the AppId, AppMutex and AppUserModelID keep their DocScan-era values: 1.0.2 is updated in place
AppName=Harf OCR
AppVerName=Harf OCR {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=Harf OCR
; the setup file's own details (Properties > Details); code signing (SignPath) checks the name and version
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Harf OCR
VersionInfoDescription=Harf OCR Setup
VersionInfoCompany=Harf OCR
VersionInfoCopyright=MIT License
AppPublisherURL=https://github.com/{#Repo}
AppSupportURL=https://github.com/{#Repo}/issues
AppUpdatesURL=https://github.com/{#Repo}/releases
DefaultDirName={localappdata}\Programs\Harf OCR
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\build\out
OutputBaseFilename=HarfOCR-Setup-{#AppVersion}
SetupIconFile=..\build\DocScan\docscan.ico
UninstallDisplayIcon={app}\docscan.ico
UninstallDisplayName=Harf OCR
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
; four ultra64 threads need about 3 GB, more than the 32-bit compiler can hold ("Out of memory" on PaddleOCR's
; libpaddle.pyd): the compressor runs in its own 64-bit process instead
LZMAUseSeparateProcess=yes
WizardStyle=modern
; the program's own single-instance mutex: setup asks to close a running copy
AppMutex=Local\DocScan.single
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
; Arabic.isl is Inno Setup's Arabic translation (the workflow downloads it next to this file)
Name: "ar"; MessagesFile: "Arabic.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ar.CoreDesc=البرنامج مع قارئَي Tesseract و PaddleOCR
en.CoreDesc=The program, with the Tesseract and PaddleOCR readers
ar.HeavyDesc=قارئ Nuqta (الأدق للعربية) و EasyOCR، تنزيل نحو 2 جيجابايت
en.HeavyDesc=Nuqta (most accurate for Arabic) and EasyOCR readers, about a 2 GB download
ar.Downloading=تنزيل القرّاء الإضافيين…
en.Downloading=Downloading the extra readers…
ar.Unpacking=فك ضغط القرّاء الإضافيين…
en.Unpacking=Unpacking the extra readers…
ar.DownloadFailed=تعذر تنزيل القرّاء الإضافيين. يكتمل التثبيت من دونهم، ويمكن تنزيلهم لاحقاً من إعدادات البرنامج.
en.DownloadFailed=The extra readers could not be downloaded. Setup finishes without them; you can add them later from the program's Settings.
ar.Open=تشغيل البرنامج
en.Open=Open Harf OCR

[Types]
Name: "full"; Description: "{cm:CoreDesc} + Nuqta + EasyOCR"
Name: "compact"; Description: "{cm:CoreDesc}"
Name: "custom"; Description: "Custom"; Flags: iscustom

[Components]
Name: "core"; Description: "{cm:CoreDesc}"; Types: full compact custom; Flags: fixed
Name: "heavy"; Description: "{cm:HeavyDesc}"; Types: full; ExtraDiskSpaceRequired: 4000000000

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\DocScan\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: core

[InstallDelete]
; an update replaces the program's own code; the readers' models and the user's data stay
Type: filesandordirs; Name: "{app}\app"
; the shortcuts from when it was called DocScan (1.0.2 and before)
Type: files; Name: "{autoprograms}\DocScan.lnk"
Type: files; Name: "{autodesktop}\DocScan.lnk"

[Icons]
Name: "{autoprograms}\Harf OCR"; Filename: "{app}\HarfOCR.exe"; WorkingDir: "{app}"; IconFilename: "{app}\docscan.ico"; AppUserModelID: "Eyasbzour.DocScan"
Name: "{autodesktop}\Harf OCR"; Filename: "{app}\HarfOCR.exe"; WorkingDir: "{app}"; IconFilename: "{app}\docscan.ico"; AppUserModelID: "Eyasbzour.DocScan"; Tasks: desktopicon

[Run]
; also after a silent update (the program closed itself for it), so it opens again
Filename: "{app}\HarfOCR.exe"; WorkingDir: "{app}"; Description: "{cm:Open}"; Flags: nowait postinstall

[INI]
; the language setup ran in becomes the program's first language (desktop/app.py language()). A fresh install only:
; a silent update picks its language from Windows, and must not change the program's.
Filename: "{app}\lang.ini"; Section: "program"; Key: "lang"; String: "{language}"; Check: IsFreshInstall

[UninstallDelete]
Type: files; Name: "{app}\lang.ini"
Type: filesandordirs; Name: "{app}\parts"
; cloudflared.exe, downloaded the first time the program is used on a phone (server/remote.py)
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\models"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  Fresh: Boolean;

// before anything is installed: no earlier copy of the program (its uninstall entry; the GUID is AppId above)
function InitializeSetup: Boolean;
begin
  Fresh := not RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F2B8C4E-1D7A-4E59-9C1B-3A5E7D2F8B90}_is1');
  Result := True;
end;

function IsFreshInstall: Boolean;
begin
  Result := Fresh;
end;

function HeavyInstalled: Boolean;
var
  V: AnsiString;
begin
  Result := LoadStringFromFile(ExpandConstant('{app}\parts\heavy\VERSION'), V) and (Trim(String(V)) = '{#HeavyVersion}');
end;

function NeedHeavy: Boolean;
begin
  Result := WizardIsComponentSelected('heavy') and not HeavyInstalled;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), CustomMessage('Downloading'), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and NeedHeavy then begin
    DownloadPage.Clear;
    DownloadPage.Add('{#Release}/HarfOCR-part-heavy.zip', 'HarfOCR-part-heavy.zip', '');
    DownloadPage.Add('{#Release}/HarfOCR-part-models.zip', 'HarfOCR-part-models.zip', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        if not WizardSilent then
          MsgBox(CustomMessage('DownloadFailed'), mbInformation, MB_OK);
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

procedure Unpack(Zip, Dir: String);
var
  Code: Integer;
begin
  if FileExists(ExpandConstant('{tmp}\' + Zip)) then begin
    ForceDirectories(Dir);
    // Windows' own tar unpacks zips, and quickly
    Exec(ExpandConstant('{sys}\tar.exe'), '-xf "' + ExpandConstant('{tmp}\' + Zip) + '" -C "' + Dir + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and NeedHeavy then begin
    WizardForm.StatusLabel.Caption := CustomMessage('Unpacking');
    DelTree(ExpandConstant('{app}\parts\heavy'), True, True, True);
    Unpack('HarfOCR-part-heavy.zip', ExpandConstant('{app}\parts\heavy'));
    Unpack('HarfOCR-part-models.zip', ExpandConstant('{app}\models'));
  end;
end;
