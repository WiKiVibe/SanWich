$ErrorActionPreference = "Continue"
$Destination = Join-Path $PSScriptRoot "_diar_candidates"
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$models = @(
    @{ Remote = "3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx"; Local = "eres2netv2.onnx" },
    @{ Remote = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"; Local = "eres2net_base.onnx" },
    @{ Remote = "wespeaker_zh_cnceleb_resnet34_LM.onnx"; Local = "wespeaker_resnet34.onnx" }
)
foreach ($model in $models) {
    $url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/$($model.Remote)"
    $target = Join-Path $Destination $model.Local
    try {
        Write-Host "正在下載 $($model.Local)…"
        Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing
        Write-Host "完成：$($model.Local)"
    } catch {
        Write-Warning "下載失敗：$($model.Local)"
    }
}
if ($Host.Name -notmatch "ServerRemoteHost") { [void](Read-Host "按 Enter 關閉") }
