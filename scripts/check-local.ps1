param(
    [string]$Python = 'python',
    [string]$ApiUrl = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$envFile = Join-Path $projectRoot '.env'
$required = @('fastapi', 'uvicorn', 'langchain_core', 'langchain_openai', 'langgraph', 'chromadb', 'FlagEmbedding', 'torch', 'pydantic_settings')

try {
    $probe = 'import importlib.util,json; names=' + (ConvertTo-Json -Compress -InputObject $required) + '; print(json.dumps({name:bool(importlib.util.find_spec(name)) for name in names}))'
    $moduleStates = (& $Python -c $probe | ConvertFrom-Json -AsHashtable)
    if ($LASTEXITCODE -ne 0 -or !$moduleStates) { throw 'Python 模块检查未完成' }
    $missing = @($required | Where-Object { !$moduleStates[$_] })
    Write-Output "python_core_modules_ready=$($missing.Count -eq 0)"
    if ($missing.Count) { Write-Output "missing_modules=$($missing -join ',')" }
} catch {
    Write-Output 'python_core_modules_ready=False'
    Write-Output 'python_probe_error=True'
    $missing = @('python-probe')
}

$lines = if (Test-Path -LiteralPath $envFile) { @(Get-Content -LiteralPath $envFile) } else { @() }
Write-Output "env_file_present=$([bool]$lines.Count)"

function Get-ConfigValue([string]$Key) {
    $line = $lines | Where-Object { $_ -match ('^\s*' + [regex]::Escape($Key) + '\s*=') } | Select-Object -Last 1
    if (!$line) { return '' }
    return (($line -split '=', 2)[1].Trim().Trim('"').Trim("'"))
}

$keyValue = Get-ConfigValue 'OPENAI_API_KEY'
$keyConfigured = [bool]($keyValue -and $keyValue -notin @('sk-xxx', 'your-key', '<api-key>'))
Write-Output "llm_key_configured=$keyConfigured"

$modelFilesReady = $true
foreach ($key in @('BGE_MODEL_PATH', 'BGE_RERANKER_PATH')) {
    $configured = Get-ConfigValue $key
    $localModel = [bool]($configured -match '(^[.\\/]|^[a-zA-Z]:|^models[\\/])')
    if (!$localModel) {
        Write-Output "${key}_local=False"
        continue
    }
    $modelDir = if ([IO.Path]::IsPathRooted($configured)) { $configured } else { Join-Path $projectRoot $configured }
    $hasConfig = Test-Path -LiteralPath (Join-Path $modelDir 'config.json')
    $hasWeights = @('model.safetensors', 'pytorch_model.bin') | Where-Object { Test-Path -LiteralPath (Join-Path $modelDir $_) }
    $ready = $hasConfig -and [bool]$hasWeights
    Write-Output "${key}_local_files_ready=$ready"
    if (!$ready) { $modelFilesReady = $false }
}

try {
    $status = (Invoke-WebRequest -Uri ($ApiUrl.TrimEnd('/') + '/health/ready') -SkipHttpErrorCheck -TimeoutSec 4).StatusCode
    Write-Output "api_model_ready_http=$status"
} catch {
    Write-Output 'api_model_ready_http=unavailable'
}

if ($missing.Count -or !$modelFilesReady) { exit 1 }
