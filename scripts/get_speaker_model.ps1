# Download the speaker-recognition model used for diarization.
#
# WeSpeaker ResNet34-LM, trained on VoxCeleb, exported to ONNX. 25MB, Apache-2.0,
# no account and no token - which is the whole reason it is used here instead of
# pyannote, whose pretrained pipelines are gated behind a HuggingFace login.
#
# It runs on onnxruntime, which is already installed as a faster-whisper
# dependency, so this needs no PyTorch.
#
# Optional: without it the app falls back to hand-built features automatically.
# Measured on the seed meetings - hand-built 89.2%, this model 95.7%.
#
# Keep this file pure ASCII (Windows PowerShell 5.1 decodes .ps1 as Windows-1252).
#
# Usage: .\scripts\get_speaker_model.ps1

$ErrorActionPreference = 'Stop'

$Root  = Split-Path -Parent $PSScriptRoot
$Dest  = Join-Path $Root 'storage\models\wespeaker.onnx'
$Url   = 'https://huggingface.co/onnx-community/wespeaker-voxceleb-resnet34-LM/resolve/main/onnx/model.onnx'

if (Test-Path $Dest) {
    $mb = [math]::Round((Get-Item $Dest).Length / 1MB, 1)
    Write-Host "Already present: $Dest ($mb MB)" -ForegroundColor Green
    exit 0
}

Write-Host 'Downloading WeSpeaker ResNet34 (25MB)...' -ForegroundColor Cyan
& (Join-Path $PSScriptRoot 'fetch.ps1') -Url $Url -OutFile $Dest -ExpectedMB 25

if (Test-Path $Dest) {
    $mb = [math]::Round((Get-Item $Dest).Length / 1MB, 1)
    Write-Host ""
    Write-Host "Speaker model ready ($mb MB). Diarization will use it automatically." -ForegroundColor Green
} else {
    Write-Host "Download failed. The app will fall back to hand-built features." -ForegroundColor Yellow
    exit 1
}
