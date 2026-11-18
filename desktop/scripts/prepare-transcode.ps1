param(
    [Parameter(Mandatory = $true)][string]$FfmpegArchive,
    [string]$Destination = (Join-Path $PSScriptRoot '../src-tauri/resources/tools')
)
$ErrorActionPreference = 'Stop'

function Assert-Sha256([string]$Path, [string]$Expected) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
    if ($actual -ne $Expected) { throw "SHA-256 mismatch for ${Path}. Expected $Expected, got $actual." }
}

$archive = (Resolve-Path -LiteralPath $FfmpegArchive).Path
$temporaryRoot = [IO.Path]::GetTempPath()
$temporary = Join-Path $temporaryRoot ('music-core-transcode-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $stagedArchive = Join-Path $temporary 'input.zip'
    Copy-Item -LiteralPath $archive -Destination $stagedArchive
    Assert-Sha256 $stagedArchive 'fc99b877603e7f4cec61a825d738eeb2cf4bbffa378cc663517600ddbd7c1c61'
    $extracted = Join-Path $temporary 'extracted'
    Expand-Archive -LiteralPath $stagedArchive -DestinationPath $extracted
    $source = Join-Path $extracted 'ffmpeg-master-latest-win64-lgpl-audio'
    $ffmpeg = Join-Path $source 'bin/ffmpeg.exe'
    $ffprobe = Join-Path $source 'bin/ffprobe.exe'
    $license = Join-Path $source 'LICENSE.txt'
    Assert-Sha256 $ffmpeg '838e351efcf53daf22a054fa5c75305d0337a3f602ecff0c9afc5e5314271115'
    Assert-Sha256 $ffprobe '16a4f492cdc7c6138de06c286fdfe12458181a7f04b49658d72559d24e807152'
    if (!(Test-Path -LiteralPath $license -PathType Leaf)) { throw "Missing $license" }
    $encoders = & $ffmpeg -hide_banner -encoders
    if ($LASTEXITCODE -ne 0 -or !($encoders -match '\blibmp3lame\b')) { throw 'FFmpeg must support libmp3lame' }

    $readme = Join-Path $temporary 'FFmpeg-README.txt'
    @(
        'Xiragi FFmpeg Audio Builds, autobuild-2026-11-01-14-17; build repository commit 8af875620b8aa273a471dc59a7981d6affd0a92f.'
        'FFmpeg N-128274-g83572f1315-20261101: https://github.com/FFmpeg/FFmpeg/commit/83572f1315'
        'Build source: https://github.com/Xiragi/FFmpeg-Audio-Builds ; build configuration: ffmpeg -buildconf.'
        'License: GNU LGPL v3; see FFmpeg-LICENSE.'
    ) | Set-Content -Encoding ascii -LiteralPath $readme

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -LiteralPath $ffmpeg, $ffprobe, $readme -Destination $Destination
    Copy-Item -LiteralPath $license -Destination (Join-Path $Destination 'FFmpeg-LICENSE')
    Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Destination 'ffmpeg.exe'), (Join-Path $Destination 'ffprobe.exe') | Format-Table
} finally {
    $resolved = (Resolve-Path -LiteralPath $temporary).Path
    $parent = (Resolve-Path -LiteralPath $temporaryRoot).Path.TrimEnd('\', '/')
    if ((Split-Path -Parent $resolved).TrimEnd('\', '/') -eq $parent -and
        (Split-Path -Leaf $resolved) -match '^music-core-transcode-[0-9a-f]{32}$') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
