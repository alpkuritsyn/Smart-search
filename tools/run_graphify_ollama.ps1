param(
    [Parameter(Mandatory = $false)]
    [string]$CorpusPath = ".",

    [Parameter(Mandatory = $false)]
    [string]$Model = "gemma4:e2b",

    [Parameter(Mandatory = $false)]
    [string]$OllamaBaseUrl = "http://localhost:11434/v1",

    [Parameter(Mandatory = $false)]
    [int]$NumCtx = 32768,

    [Parameter(Mandatory = $false)]
    [int]$ApiTimeoutSeconds = 600,

    [Parameter(Mandatory = $false)]
    [string]$OutputRoot = "",

    [Parameter(Mandatory = $false)]
    [switch]$SkipModelSmokeTest
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $CorpusPath)) {
    throw "Corpus path does not exist: $CorpusPath"
}

$resolvedCorpus = (Resolve-Path -LiteralPath $CorpusPath).Path
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $resolvedOutput = $resolvedCorpus
} else {
    if (-not (Test-Path -LiteralPath $OutputRoot)) {
        New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    }
    $resolvedOutput = (Resolve-Path -LiteralPath $OutputRoot).Path
}

$graphify = Get-Command graphify -ErrorAction SilentlyContinue
$graphifyPython = $null
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -ne $uv) {
    try {
        $uvToolRoot = (& $uv.Source tool dir 2>$null | Select-Object -First 1).Trim()
        $candidatePython = Join-Path $uvToolRoot "graphifyy\Scripts\python.exe"
        if (Test-Path -LiteralPath $candidatePython -PathType Leaf) {
            & $candidatePython -c "import graphify" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $graphifyPython = $candidatePython
            }
        }
    } catch {
        $graphifyPython = $null
    }
}
if ($null -eq $graphifyPython -and $null -eq $graphify) {
    throw "Graphify is not available. Install graphifyy with its OpenAI-compatible backend support, then retry."
}

$apiRoot = $OllamaBaseUrl.TrimEnd('/')
if ($apiRoot.EndsWith('/v1')) {
    $apiRoot = $apiRoot.Substring(0, $apiRoot.Length - 3)
}

try {
    $tags = Invoke-RestMethod -Method Get -Uri "$apiRoot/api/tags" -TimeoutSec 15
} catch {
    throw "Ollama API is not reachable at $apiRoot. Start Ollama and retry. Details: $($_.Exception.Message)"
}

$availableModels = @($tags.models | ForEach-Object { $_.name })
if ($availableModels -notcontains $Model) {
    $availableText = if ($availableModels.Count -gt 0) { $availableModels -join ', ' } else { '<none>' }
    throw "Exact Ollama model tag '$Model' is not installed. Available: $availableText. Verify the requested tag through /api/tags or 'ollama list'. Do not silently substitute another model."
}

if (-not $SkipModelSmokeTest) {
    $smokeBody = @{
        model = $Model
        stream = $false
        think = $false
        format = "json"
        messages = @(
            @{ role = "user"; content = 'Return JSON only: {"ok":true,"purpose":"graphify_preflight"}' }
        )
        options = @{ temperature = 0; num_ctx = [Math]::Min($NumCtx, 8192); num_predict = 512 }
    } | ConvertTo-Json -Depth 6
    try {
        $smoke = Invoke-RestMethod -Method Post -Uri "$apiRoot/api/chat" -ContentType "application/json" -Body $smokeBody -TimeoutSec 240
    } catch {
        throw "Ollama model preflight failed for '$Model': $($_.Exception.Message)"
    }
    if ([string]::IsNullOrWhiteSpace([string]$smoke.message.content)) {
        throw "Ollama model '$Model' returned an empty preflight response (done_reason=$($smoke.done_reason))."
    }
    Write-Output "Ollama model preflight: OK"
}

$env:OLLAMA_BASE_URL = $OllamaBaseUrl
$env:OLLAMA_MODEL = $Model
$env:OLLAMA_API_KEY = "ollama"
$env:GRAPHIFY_OLLAMA_NUM_CTX = [string]$NumCtx
$env:GRAPHIFY_OLLAMA_KEEP_ALIVE = "30m"
$env:GRAPHIFY_OLLAMA_PARALLEL = ""

if ($null -ne $graphifyPython) {
    Write-Output "Graphify runtime: $graphifyPython -m graphify"
} else {
    Write-Output "Graphify executable: $($graphify.Source)"
}
Write-Output "Corpus: $resolvedCorpus"
Write-Output "Output root: $resolvedOutput"
Write-Output "Ollama endpoint: $OllamaBaseUrl"
Write-Output "Ollama model: $Model"
Write-Output "Context: $NumCtx"

if ($null -ne $graphifyPython) {
    & $graphifyPython -m graphify extract $resolvedCorpus `
        --backend ollama `
        --model $Model `
        --out $resolvedOutput `
        --max-concurrency 1 `
        --max-workers 1 `
        --api-timeout $ApiTimeoutSeconds
} else {
    & $graphify.Source extract $resolvedCorpus `
        --backend ollama `
        --model $Model `
        --out $resolvedOutput `
        --max-concurrency 1 `
        --max-workers 1 `
        --api-timeout $ApiTimeoutSeconds
}

if ($LASTEXITCODE -ne 0) {
    throw "Graphify extraction failed with exit code $LASTEXITCODE"
}

$graphPath = Join-Path $resolvedOutput "graphify-out\graph.json"
if (-not (Test-Path -LiteralPath $graphPath)) {
    throw "Graphify finished without expected graph: $graphPath"
}

Write-Output "Graph built: $graphPath"
Write-Output "Next: run structural validation, prepare the Antigravity review packet, then launch the independent reviewer subagent."
