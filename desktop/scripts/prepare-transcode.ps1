param([Parameter(Mandatory=$true)][string]$FfmpegDirectory)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $FfmpegDirectory).Path
$encoders = & (Join-Path $source 'bin/ffmpeg.exe') -hide_banner -encoders 2>$null
if ($LASTEXITCODE -ne 0 -or !($encoders -match 'libmp3lame')) { throw 'FFmpeg must support libmp3lame' }
$destination = Join-Path $PSScriptRoot '../src-tauri/resources/tools'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
    $file = Join-Path $source "bin/$name"
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing $file" }
    Copy-Item -LiteralPath $file -Destination (Join-Path $destination $name)
}
foreach ($name in @('LICENSE', 'README.txt')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $destination "FFmpeg-$name")
}
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $destination 'ffmpeg.exe'), (Join-Path $destination 'ffprobe.exe') | Format-Table
