# Architected and built by dr Classy
param(
    [string]$SourcePng = "..\public\icons\sidelab.png"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

function New-SquarePng {
    param(
        [Parameter(Mandatory = $true)]
        [System.Drawing.Image]$SourceImage,
        [Parameter(Mandatory = $true)]
        [int]$Size,
        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $bitmap = New-Object System.Drawing.Bitmap $Size, $Size
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $graphics.DrawImage($SourceImage, 0, 0, $Size, $Size)

        $parent = Split-Path -Parent $OutputPath
        if ($parent) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function New-ScaledPng {
    param(
        [Parameter(Mandatory = $true)]
        [System.Drawing.Image]$SourceImage,
        [Parameter(Mandatory = $true)]
        [int]$Width,
        [Parameter(Mandatory = $true)]
        [int]$Height,
        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $bitmap = New-Object System.Drawing.Bitmap $Width, $Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $graphics.DrawImage($SourceImage, 0, 0, $Width, $Height)

        $parent = Split-Path -Parent $OutputPath
        if ($parent) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function New-IcoFromPngs {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$PngPaths,
        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $entries = @()
    foreach ($pngPath in $PngPaths) {
        $bytes = [System.IO.File]::ReadAllBytes($pngPath)
        $image = [System.Drawing.Image]::FromFile($pngPath)
        try {
            $entries += [pscustomobject]@{
                Width  = $image.Width
                Height = $image.Height
                Bytes  = $bytes
            }
        } finally {
            $image.Dispose()
        }
    }

    $stream = [System.IO.File]::Create($OutputPath)
    $writer = New-Object System.IO.BinaryWriter($stream)
    try {
        $writer.Write([UInt16]0)
        $writer.Write([UInt16]1)
        $writer.Write([UInt16]$entries.Count)

        $offset = 6 + (16 * $entries.Count)
        foreach ($entry in $entries) {
            $writer.Write([byte]($(if ($entry.Width -ge 256) { 0 } else { $entry.Width })))
            $writer.Write([byte]($(if ($entry.Height -ge 256) { 0 } else { $entry.Height })))
            $writer.Write([byte]0)
            $writer.Write([byte]0)
            $writer.Write([UInt16]1)
            $writer.Write([UInt16]32)
            $writer.Write([UInt32]$entry.Bytes.Length)
            $writer.Write([UInt32]$offset)
            $offset += $entry.Bytes.Length
        }

        foreach ($entry in $entries) {
            $writer.Write($entry.Bytes)
        }
    } finally {
        $writer.Dispose()
        $stream.Dispose()
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")
$resolvedSource = Resolve-Path (Join-Path $scriptDir $SourcePng)

$publicIconsDir = Join-Path $root "public\icons"
$installerAssetsDir = Join-Path $root "installer\assets"

$appSourcePath = Join-Path $publicIconsDir "sidelab.png"
$logoSourcePath = Join-Path $publicIconsDir "sidelab-logo.png"
$horizontalSourcePath = Join-Path $publicIconsDir "sidelab-logo2.png"
$verticalSourcePath = Join-Path $publicIconsDir "sidelab-logo3.png"

$appIconSizes = @(16, 24, 32, 48, 64, 128, 256, 512)
$logoSizes = @(16, 32, 64, 128, 256, 512)
$faviconSizes = @(16, 32)
$faviconIcoSizes = @(16, 32, 48)
$appleTouchSize = 180
$horizontalVariants = [ordered]@{
    "sidelab-horizontal-sm.png" = @(640, 360)
    "sidelab-horizontal-md.png" = @(1024, 576)
    "sidelab-horizontal-lg.png" = @(1600, 900)
}
$verticalVariants = [ordered]@{
    "sidelab-vertical-128.png" = @(128, 128)
    "sidelab-vertical-256.png" = @(256, 256)
    "sidelab-vertical-512.png" = @(512, 512)
}

$sourceImage = [System.Drawing.Image]::FromFile($appSourcePath)
try {
    foreach ($size in $appIconSizes) {
        New-SquarePng -SourceImage $sourceImage -Size $size -OutputPath (Join-Path $publicIconsDir "sidelab-$size.png")
    }

    foreach ($size in $faviconSizes) {
        New-SquarePng -SourceImage $sourceImage -Size $size -OutputPath (Join-Path $publicIconsDir "favicon-$size.png")
    }

    New-SquarePng -SourceImage $sourceImage -Size $appleTouchSize -OutputPath (Join-Path $publicIconsDir "apple-touch-icon.png")
} finally {
    $sourceImage.Dispose()
}

$logoImage = [System.Drawing.Image]::FromFile($logoSourcePath)
try {
    foreach ($size in $logoSizes) {
        New-SquarePng -SourceImage $logoImage -Size $size -OutputPath (Join-Path $publicIconsDir "sidelab-logo-$size.png")
    }
} finally {
    $logoImage.Dispose()
}

$horizontalImage = [System.Drawing.Image]::FromFile($horizontalSourcePath)
try {
    foreach ($variant in $horizontalVariants.GetEnumerator()) {
        New-ScaledPng -SourceImage $horizontalImage -Width $variant.Value[0] -Height $variant.Value[1] -OutputPath (Join-Path $publicIconsDir $variant.Key)
    }

    New-ScaledPng -SourceImage $horizontalImage -Width 1200 -Height 630 -OutputPath (Join-Path $publicIconsDir "og.png")
} finally {
    $horizontalImage.Dispose()
}

$verticalImage = [System.Drawing.Image]::FromFile($verticalSourcePath)
try {
    foreach ($variant in $verticalVariants.GetEnumerator()) {
        New-ScaledPng -SourceImage $verticalImage -Width $variant.Value[0] -Height $variant.Value[1] -OutputPath (Join-Path $publicIconsDir $variant.Key)
    }
} finally {
    $verticalImage.Dispose()
}

$faviconPngs = foreach ($size in $faviconIcoSizes) {
    $outputPath = Join-Path $publicIconsDir "favicon-$size.png"
    if (-not (Test-Path $outputPath)) {
        $sourceImage = [System.Drawing.Image]::FromFile($resolvedSource)
        try {
            New-SquarePng -SourceImage $sourceImage -Size $size -OutputPath $outputPath
        } finally {
            $sourceImage.Dispose()
        }
    }
    $outputPath
}

$icoPngs = foreach ($size in @(16, 24, 32, 48, 64, 128, 256)) {
    Join-Path $publicIconsDir "sidelab-$size.png"
}

New-IcoFromPngs -PngPaths $faviconPngs -OutputPath (Join-Path $publicIconsDir "favicon.ico")
New-IcoFromPngs -PngPaths $icoPngs -OutputPath (Join-Path $installerAssetsDir "sidelab.ico")
