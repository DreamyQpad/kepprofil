# Telepito epitese: powershell -ExecutionPolicy Bypass -File build.ps1
# 1) ikon  2) PyInstaller csomag  3) Inno Setup -> out\Kijelzo-telepito.exe  4) masolat a Dokumentumok\telepitok mappaba
$ErrorActionPreference = 'Continue'   # a PyInstaller az allapotuzeneteit a hibacsatornan irja, ez nem hiba
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "$root\.venv\Scripts\python.exe"
$b = "$root\build_installer"
$iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"

Set-Location $root
& $py "$root\make_icon.py"
if ($LASTEXITCODE -ne 0) { throw 'Ikon-keszites hiba' }

& $py -m PyInstaller --noconfirm --clean --onedir --noconsole --name Kepprofil --icon "$root\assets\icon.ico" `
  --distpath "$b\dist" --workpath "$b\work" --specpath "$b" --paths $root `
  --add-data "$root\assets;assets" `
  --collect-all customtkinter --collect-all openrgb --collect-submodules pystray --hidden-import pystray._win32 `
  --hidden-import psutil `
  "$root\kijelzo.py" *> "$b\pyinstaller.log"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller hiba, lasd: $b\pyinstaller.log" }

if (-not (Test-Path $iscc)) { throw 'Nincs Inno Setup: winget install --id JRSoftware.InnoSetup' }
Set-Location $b
& $iscc /Q "$b\telepito.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup hiba" }
# mindig keszul egy masolat a Dokumentumok\telepitok mappaba is
$docs = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'telepitok'
New-Item -ItemType Directory -Force $docs | Out-Null
Copy-Item "$root\out\Kepprofil-telepito.exe" $docs -Force
"Kesz: $root\out\Kepprofil-telepito.exe"
"Masolat: $docs\Kepprofil-telepito.exe"
