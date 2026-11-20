param([string]$Models = "", [switch]$Background)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Join-Path $env:LOCALAPPDATA NanoCutRuntime
$tools = Join-Path $root tools
$app = Split-Path $PSScriptRoot
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ("nanocut-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $root,$tools,$tempDir | Out-Null

Start-Transcript -Path (Join-Path $root "setup.log") -Force | Out-Null

function Download($url, $name, $sha) {
    $file = Join-Path $tempDir $name
    Invoke-WebRequest -UseBasicParsing $url -OutFile $file
    if ((Get-FileHash $file).Hash -ne $sha) { throw "Checksum failed for $name." }
    return $file
}
function Find-Tool($name, $minimum, $versionArg) {
    $candidates = @((Join-Path $tools "$name.exe")) + @(Get-Command "$name.exe" -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    foreach ($candidate in $candidates) {
        if (!(Test-Path $candidate)) { continue }
        $line = (& $candidate $versionArg | Select-Object -First 1)
        if ($line -match '(?:version\s+n?|^v)(\d+)' -and [int]$Matches[1] -ge $minimum) {
            Write-Host "Using $candidate"
            return $candidate
        }
    }
}
function Find-Python {
    $saved = Join-Path $root 'python-path.txt'
    $candidates = @()
    if (Test-Path $saved) { $candidates += Join-Path ([IO.File]::ReadAllText($saved).Trim()) python.exe }
    $candidates += Join-Path $root 'python\python.exe'
    $candidates += @(Get-Command python.exe -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    foreach ($hive in 'HKCU:', 'HKLM:') {
        foreach ($v in '3.12','3.13','3.11') {
            $reg = Get-Item "$hive\Software\Python\PythonCore\$v\InstallPath" -ErrorAction SilentlyContinue
            if ($reg -and $reg.GetValue('')) { $candidates += Join-Path ($reg.GetValue('')) python.exe }
        }
    }
    foreach ($c in ($candidates | Select-Object -Unique)) {
        if (!(Test-Path $c) -or $c -match '\\Microsoft\\WindowsApps\\') { continue }
        & $c -c "import sys,struct,tkinter,venv,pip;sys.exit(not ((3,11)<=sys.version_info[:2]<=(3,13) and struct.calcsize('P')==8))" 2>$null
        if ($LASTEXITCODE -eq 0) { return $c }
    }
}
function Packages($requirements) {
    & $python -m pip --disable-pip-version-check install --no-input -r (Join-Path $app $requirements)
    if ($LASTEXITCODE -ne 0) { throw "Unable to install missing packages from $requirements." }
}
try {
    $python = Find-Python
    if (!$python) {
        Write-Host "Installing Python for this user..."
        $file = Download 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' python.exe '67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb'
        $dir = Join-Path $root python
        $p = Start-Process $file -ArgumentList "/quiet InstallAllUsers=0 TargetDir=""$dir"" Include_pip=1 Include_tcltk=1 Include_launcher=0 AssociateFiles=0 Shortcuts=0 PrependPath=0 Include_test=0" -Wait -PassThru
        if ($p.ExitCode -notin 0,3010) { throw "Python installation failed." }
        $python = Join-Path $dir python.exe
    } elseif (!$python.StartsWith("$root\",[StringComparison]::OrdinalIgnoreCase)) {
        $envDir = Join-Path $root 'env-1.1'
        $venvPython = Join-Path $envDir 'Scripts\python.exe'
        if (!(Test-Path $venvPython)) {
            & $python -m venv --system-site-packages $envDir
            if ($LASTEXITCODE -ne 0) { throw "Could not prepare the media environment." }
        }
        $python = $venvPython
    }
    Write-Host "Using $python"
    $ffmpeg = Find-Tool ffmpeg 7 '-version'
    $ffprobe = Find-Tool ffprobe 7 '-version'
    if (!$ffmpeg -or !$ffprobe) {
        Write-Host "Downloading missing FFmpeg tools..."
        $zip = Download 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip' ffmpeg.zip '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
        Expand-Archive $zip $tempDir
        $bin = Join-Path $tempDir 'ffmpeg-9.0.2-essentials_build\bin'
        if (!$ffmpeg) { $ffmpeg = Join-Path $tools ffmpeg.exe; Copy-Item "$bin\ffmpeg.exe" $ffmpeg -Force }
        if (!$ffprobe) { $ffprobe = Join-Path $tools ffprobe.exe; Copy-Item "$bin\ffprobe.exe" $ffprobe -Force }
    }
    $node = Find-Tool node 22 '--version'
    $deno = Get-Command deno.exe -ErrorAction SilentlyContinue
    if (!$node -and $deno) {
        $dv = (& $deno.Source --version | Select-Object -First 1)
        if ($dv -match 'deno (\d+\.\d+\.\d+)' -and [version]$Matches[1] -ge [version]'2.3.0') { $node = $deno.Source }
    }
    if (!$node) {
        $url = 'https://nodejs.org/dist/latest-v24.x'
        $sums = (Invoke-WebRequest -UseBasicParsing "$url/SHASUMS256.txt").Content
        if ($sums -is [byte[]]) { $sums = [Text.Encoding]::UTF8.GetString($sums) }
        if ($sums -notmatch '(?m)^([a-fA-F0-9]{64})\s+win-x64/node\.exe\s*$') { throw "Invalid Node.js release manifest." }
        $file = Download "$url/win-x64/node.exe" node.exe $Matches[1]
        $node = Join-Path $tools node.exe
        Move-Item $file $node -Force
    }
    $paths = @($ffmpeg,$ffprobe,$node | ForEach-Object { Split-Path $_ } | Select-Object -Unique)
    $env:PATH = ($paths -join ';') + ';' + $env:PATH
    Packages 'requirements.txt'
    $foregroundReady = Join-Path $root "foreground-ready"
    $selected = @($Models.Split(',') | Where-Object { $_ })
    if ($selected.Count -gt 0 -or $Background) {
        Packages 'requirements-ai.txt'
        foreach ($m in $selected) {
            Write-Host "Preparing Whisper $m..."
            & $python (Join-Path $PSScriptRoot 'models.py') $m
            if ($LASTEXITCODE -ne 0) { throw "Could not prepare Whisper $m." }
        }
        if ($Background) {
            & $python (Join-Path $PSScriptRoot 'models.py') foreground
            if ($LASTEXITCODE -ne 0) { throw "Could not prepare the background model." }
            Set-Content $foregroundReady "1"
        }
    }
    $hostExe = Join-Path $app NanoCut.exe
    $probe = Start-Process $hostExe -ArgumentList '--check-webview' -Wait -PassThru
    if ($probe.ExitCode -ne 0) {
        Write-Host "Installing Microsoft WebView2 Runtime..."
        $file = Join-Path $tempDir WebView2Setup.exe
        Invoke-WebRequest -UseBasicParsing 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $file
        $signature = Get-AuthenticodeSignature $file
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'Invalid Microsoft installer signature.' }
        $p = Start-Process $file -ArgumentList '/silent /install' -Wait -PassThru
        if ((Start-Process $hostExe -ArgumentList '--check-webview' -Wait -PassThru).ExitCode -ne 0) { throw 'WebView2 installation failed.' }
    }
    $config = Join-Path $root 'runtime-1.1.json'
    @{python=$python; paths=$paths} | ConvertTo-Json | Out-File "$config.new" -Encoding utf8
    Move-Item "$config.new" $config -Force
    Write-Host "NanoCut 1.1 is ready."
} finally {
    Stop-Transcript | Out-Null
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
