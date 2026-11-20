param([switch]$AI)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Join-Path $env:LOCALAPPDATA "NanoCutRuntime"
$tools = Join-Path $root "tools"
$pythonDir = Join-Path $root "python"
$pythonExe = Join-Path $pythonDir "python.exe"
$src = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path $root,$tools | Out-Null
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ("nanocut-setup-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tempDir | Out-Null

function Get-VerifiedFile($url, $target, $hash) {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $target
    if ((Get-FileHash -Algorithm SHA256 -Path $target).Hash -ne $hash) {
        throw "The downloaded file failed its SHA-256 check. Retry setup."
    }
}
function Install-Packages($file) {
    & $pythonExe -m pip install --disable-pip-version-check -r (Join-Path $src $file)
    if ($LASTEXITCODE -ne 0) { throw "Python packages could not be installed." }
}
try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw "NanoCut requires 64-bit Windows." }
    $saved = Join-Path $root "python-path.txt"
    if (Test-Path $saved) {
        $candidate = [IO.File]::ReadAllText($saved).Trim()
        if (Test-Path (Join-Path $candidate "python.exe")) {
            $pythonDir = $candidate
            $pythonExe = Join-Path $candidate "python.exe"
        }
    }
    if (-not (Test-Path $pythonExe)) {
        $existing = $null
        foreach ($hive in @("HKCU:", "HKLM:")) {
            $reg = Get-Item "$hive\Software\Python\PythonCore\3.12\InstallPath" -ErrorAction SilentlyContinue
            if ($null -ne $reg) {
                $candidate = Join-Path ($reg.GetValue('')) "python.exe"
                if (Test-Path $candidate) { $existing = $candidate; break }
            }
        }
        if ($existing) {
            Write-Host "Creating a private NanoCut environment with the installed Python..."
            & $existing -m venv (Join-Path $root "env")
            if ($LASTEXITCODE -ne 0) { throw "Could not create a private Python environment." }
            $pythonDir = Join-Path $root "env\Scripts"
            $pythonExe = Join-Path $pythonDir "python.exe"
        } else {
            Write-Host "Installing the private NanoCut Python runtime..."
            $installer = Join-Path $tempDir "python.exe"
            Get-VerifiedFile "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" $installer "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"
            $argsList = "/quiet InstallAllUsers=0 TargetDir=""$pythonDir"" Include_pip=1 Include_tcltk=1 Include_launcher=0 AssociateFiles=0 Shortcuts=0 PrependPath=0 Include_test=0"
            $result = Start-Process $installer -ArgumentList $argsList -Wait -PassThru
            if ($result.ExitCode -notin 0,3010 -or -not (Test-Path $pythonExe)) { throw "Python setup failed." }
        }
    }
    $envFile = Join-Path $root "python-path.txt"
    [IO.File]::WriteAllText($envFile, $pythonDir)
    if (-not (Test-Path (Join-Path $tools "ffprobe.exe")) -or -not (Test-Path (Join-Path $tools "ffmpeg.exe"))) {
        Write-Host "Downloading FFmpeg and ffprobe..."
        $archive = Join-Path $tempDir "ffmpeg.zip"
        Get-VerifiedFile "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip" $archive "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
        Expand-Archive -LiteralPath $archive -DestinationPath $tempDir
        $bin = Join-Path $tempDir "ffmpeg-9.0.2-essentials_build\bin"
        Copy-Item (Join-Path $bin "ffmpeg.exe"),(Join-Path $bin "ffprobe.exe") -Destination $tools -Force
    }
    $env:PATH = "$tools;$env:PATH"
    & (Join-Path $tools "ffmpeg.exe") -version | Select-Object -First 1
    if (-not (Test-Path (Join-Path $tools "node.exe"))) {
        Write-Host "Installing the JavaScript runtime used by yt-dlp..."
        $nodeBase = "https://nodejs.org/dist/latest-v24.x"
        $sums = (Invoke-WebRequest -UseBasicParsing "$nodeBase/SHASUMS256.txt").Content
        if ($sums -is [byte[]]) { $sums = [Text.Encoding]::UTF8.GetString($sums) }
        $match = [regex]::Match($sums, '(?m)^([a-fA-F0-9]{64})\s+win-x64/node\.exe\s*$')
        if (-not $match.Success) { throw "Could not verify the Node.js release manifest." }
        Get-VerifiedFile "$nodeBase/win-x64/node.exe" (Join-Path $tempDir "node.exe") $match.Groups[1].Value
        Move-Item (Join-Path $tempDir "node.exe") (Join-Path $tools "node.exe") -Force
    }
    Install-Packages "requirements.txt"
    if ($AI) { Write-Host "Installing local CPU AI tools..."; Install-Packages "requirements-ai.txt" }
    Set-Content -Encoding ASCII -Path (Join-Path $root "ready-v1") -Value "1"
    Write-Host "NanoCut is ready."
}
finally {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}

