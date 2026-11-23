# Builds the Windows program folder (build\DocScan) that the installer (desktop\installer.iss) packs.
#   .\desktop\build.ps1 -Version 1.0.0            base program: Tesseract + PaddleOCR (Tesseract from $env:TESSERACT_DIR
#                                                 or C:\Program Files\Tesseract-OCR; the GitHub workflow installs it)
#   .\desktop\build.ps1 -Version 1.0.0 -Parts     also the optional readers, as zips the installer downloads:
#                                                 build\out\HarfOCR-part-heavy.zip and HarfOCR-part-models.zip
# Needs internet (Python, packages, models). The ministry letterhead template is never included.
param(
    [string]$Version = "0.0.0",
    [switch]$Parts,
    [switch]$SkipTesseract
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is many times slower with its progress bar
$Repo = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Repo "build"
$Dist = Join-Path $Build "DocScan"
$Out = Join-Path $Build "out"
$PyVersion = "3.12.10"
$Py = Join-Path $Dist "python\python.exe"

function Step($text) { Write-Host "== $text" }

Step "clean"
Remove-Item -Recurse -Force $Dist, $Out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Dist, $Out | Out-Null

Step "Python $PyVersion (embeddable)"
$zip = Join-Path $Build "python-embed.zip"
if (-not (Test-Path $zip)) {
    Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip" -OutFile $zip
}
Expand-Archive $zip (Join-Path $Dist "python")
# let it use site-packages (the embeddable build ignores them by default)
$pth = Get-ChildItem (Join-Path $Dist "python") -Filter "python*._pth" | Select-Object -First 1
(Get-Content $pth.FullName) -replace '^#\s*import site', 'import site' | Set-Content $pth.FullName -Encoding ascii
Add-Content $pth.FullName "Lib\site-packages"
$getpip = Join-Path $Build "get-pip.py"
if (-not (Test-Path $getpip)) { Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip }
& $Py $getpip --no-warn-script-location -q
if ($LASTEXITCODE) { throw "pip" }

Step "packages"
# setuptools first: some packages (pywebview's proxy_tools) ship as source, built on install
& $Py -m pip install --no-warn-script-location -q setuptools wheel
& $Py -m pip install --no-warn-script-location -q -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE) { throw "packages" }

Step "the app"
$App = Join-Path $Dist "app"
New-Item -ItemType Directory -Force (Join-Path $App "templates"), (Join-Path $App "desktop") | Out-Null
robocopy (Join-Path $Repo "server") (Join-Path $App "server") /E /XD __pycache__ tests .pytest_cache /NFL /NDL /NJH /NJS | Out-Null
robocopy (Join-Path $Repo "web") (Join-Path $App "web") /E /NFL /NDL /NJH /NJS | Out-Null
Copy-Item (Join-Path $Repo "templates\plain.*") (Join-Path $App "templates")  # only the plain template, never the letterhead
Copy-Item (Join-Path $PSScriptRoot "app.py") (Join-Path $App "desktop")
Set-Content (Join-Path $App "desktop\VERSION") $Version -Encoding ascii
# compiled now, not on the first start after each install or update (pip already did the packages)
& $Py -m compileall -q -j 0 $App | Out-Null
if ($LASTEXITCODE) { throw "compileall" }
& $Py (Join-Path $PSScriptRoot "make_icon.py") (Join-Path $Dist "docscan.ico")

Step "HarfOCR.exe (desktop\launcher.cpp)"
# zig's C++ compiler from pip, kept out of the program's own Python
$zig = Join-Path $Build "zig"
if (-not (Test-Path $zig)) { & $Py -m pip install --no-warn-script-location -q --target $zig ziglang==0.17.1; if ($LASTEXITCODE) { throw "ziglang" } }
# all on the build folder's drive: on GitHub's runner the repo is on D: and zig's cache on C:, and the icon given by
# its full path failed there (launcher.rc: FileSystemFailure); so the icon sits by launcher.rc and zig caches here too
Copy-Item (Join-Path $Dist "docscan.ico") (Join-Path $Build "launcher.ico")
Set-Content (Join-Path $Build "launcher.rc") '1 ICON "launcher.ico"' -Encoding ascii
$env:ZIG_GLOBAL_CACHE_DIR = $env:ZIG_LOCAL_CACHE_DIR = Join-Path $Build "zig-cache"
Push-Location $Build
try {
    & $Py -c "import sys; sys.path.insert(0, sys.argv[1]); import runpy; sys.argv = ['zig'] + sys.argv[2:]; runpy.run_module('ziglang', run_name='__main__')" `
        $zig c++ -std=c++17 -O2 -municode "-Wl,--subsystem,windows" -target x86_64-windows-gnu -o (Join-Path $Dist "HarfOCR.exe") `
        (Join-Path $PSScriptRoot "launcher.cpp") "launcher.rc"
} finally { Pop-Location }
if ($LASTEXITCODE) { throw "HarfOCR.exe" }

if (-not $SkipTesseract) {
    Step "Tesseract"
    $tsrc = if ($env:TESSERACT_DIR) { $env:TESSERACT_DIR } else { "C:\Program Files\Tesseract-OCR" }
    if (-not (Test-Path (Join-Path $tsrc "tesseract.exe"))) { throw "Tesseract not found in $tsrc" }
    $tdst = Join-Path $Dist "tesseract"
    robocopy $tsrc $tdst /E /XD tessdata /NFL /NDL /NJH /NJS | Out-Null
    foreach ($m in "fast", "standard", "best") {
        $dir = Join-Path $tdst "tessdata\$m"
        New-Item -ItemType Directory -Force $dir | Out-Null
        $repoName = if ($m -eq "standard") { "tessdata" } else { "tessdata_$m" }
        foreach ($l in "ara", "eng") {
            Invoke-WebRequest "https://raw.githubusercontent.com/tesseract-ocr/$repoName/main/$l.traineddata" -OutFile (Join-Path $dir "$l.traineddata")
        }
    }
}

Step "PaddleOCR models (Arabic and English)"
$env:PADDLE_PDX_CACHE_HOME = Join-Path $Dist "models\paddlex"
Push-Location (Join-Path $App "server")
& $Py -c "import sys; sys.path.insert(0, '.'); from engines import paddle_engine as e; e._get('ar'); e._get('en'); print('paddle models ready')"
if ($LASTEXITCODE) { throw "paddle models" }
Pop-Location

if ($Parts) {
    Step "optional readers: torch (CPU), EasyOCR, Nuqta"
    $heavy = Join-Path $Build "parts\heavy"
    $site = Join-Path $heavy "site-packages"
    Remove-Item -Recurse -Force $heavy -ErrorAction SilentlyContinue
    # pinned to the base program's versions: desktop\app.py puts this folder after the base packages, so a newer copy
    # of a shared one here (numpy, PyYAML) would never load, and the readers have to work with the base ones
    $pins = Join-Path $Build "base-pins.txt"
    & $Py -m pip freeze --exclude-editable | Set-Content $pins -Encoding ascii
    # one install, so torch is resolved once (a second --target install would fetch it again); CPU wheels
    & $Py -m pip install --no-warn-script-location -q --target $site torch torchvision -r (Join-Path $PSScriptRoot "requirements-heavy.txt") `
        -c $pins --extra-index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE) { throw "heavy readers" }
    # their models, through the engine code itself (same models and settings as when reading)
    $models = Join-Path $Build "parts\models"
    Remove-Item -Recurse -Force $models -ErrorAction SilentlyContinue
    $env:EASYOCR_MODELS = Join-Path $models "easyocr"
    $env:HF_HOME = Join-Path $models "hf"
    # the folder goes in as an argument: the embedded Python ignores PYTHONPATH (its ._pth file decides the path).
    # After the base packages, as desktop\app.py adds it, so this also proves the readers load as installed.
    $boot = "import sys; sys.path.append(sys.argv[1]); sys.path.insert(0, '.'); "
    # -X utf8: EasyOCR's download bar prints block characters, which the runner's console codepage (cp1252) cannot
    # encode; PYTHONIOENCODING would be ignored like PYTHONPATH
    Push-Location (Join-Path $App "server")
    & $Py -X utf8 -c ($boot + "from engines import easyocr_engine as e; e._get_reader(); print('easyocr models ready')") $site
    if ($LASTEXITCODE) { throw "easyocr models" }
    & $Py -X utf8 -c ($boot + "from engines import nuqta_engine as e; e._get(); print('nuqta model ready')") $site
    if ($LASTEXITCODE) { throw "nuqta model" }
    Pop-Location
    # where links are allowed (the runner), the Hugging Face cache links each snapshot file to a blob; a zip keeps the
    # links and a per-user install cannot make them, so the snapshots get the files themselves and the blobs go
    $hf = Join-Path $models "hf"
    Get-ChildItem $hf -Recurse -File -Attributes ReparsePoint | ForEach-Object {
        $blob = $_.ResolveLinkTarget($true).FullName
        Remove-Item $_.FullName
        Copy-Item $blob $_.FullName
    }
    Get-ChildItem $hf -Recurse -Directory -Filter blobs | Remove-Item -Recurse -Force
    $links = @(Get-ChildItem $models -Recurse -Attributes ReparsePoint)
    if ($links.Count) { throw "links left in the models: $($links[0].FullName)" }
    # the installer downloads this part only when the installed one is older (desktop\HEAVY_VERSION: bump it when
    # requirements-heavy.txt or the models change)
    Copy-Item (Join-Path $PSScriptRoot "HEAVY_VERSION") (Join-Path $heavy "VERSION")
    # two release assets (each must stay under GitHub's 2 GB): the libraries, and the Nuqta model
    tar -a -c -f (Join-Path $Out "HarfOCR-part-heavy.zip") -C $heavy site-packages VERSION
    tar -a -c -f (Join-Path $Out "HarfOCR-part-models.zip") -C $models .
}

Step "done: $Dist"
