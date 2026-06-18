<#
.SYNOPSIS
    Demonstra o fluxo completo do LocalHub entre duas pessoas, numa pasta temporaria.

.DESCRIPTION
    Cria um repositorio central (bare), simula a "Ana" criando e enviando um
    commit, a "Bia" clonando/editando/enviando, e a "Ana" puxando (fast-forward).
    Serve para validar, na sua maquina, que init/add/commit/push/clone/pull
    funcionam de ponta a ponta. Nao precisa instalar o pacote.

.PARAMETER Python
    Caminho completo para o python.exe a usar. Se omitido, detecta sozinho.

.PARAMETER Keep
    Mantem a pasta temporaria ao final (por padrao ela e apagada).

.EXAMPLE
    .\demo.ps1

.EXAMPLE
    .\demo.ps1 -Python "C:\caminho\para\python.exe" -Keep
#>
[CmdletBinding()]
param([string]$Python, [switch]$Keep)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-Python {
    param([string]$Path)
    if ($Path) {
        if (-not (Test-Path $Path)) { throw "Interpretador nao encontrado: $Path" }
        return (Resolve-Path $Path).Path
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $exe = & py -3 -c "import sys; print(sys.executable)"
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch { }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return (Get-Command python).Source
    }
    throw "Nenhum Python encontrado. Informe -Python 'C:\caminho\para\python.exe'."
}

$py = Resolve-Python -Path $Python
$env:PYTHONPATH = $here   # acha o pacote 'localhub' sem precisar instalar

function lhub {
    & $py -m localhub @args
    if ($LASTEXITCODE -ne 0) { throw "lhub falhou: $($args -join ' ')" }
}

function Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }

$root = Join-Path $env:TEMP ("lhub_demo_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $root | Out-Null
$start = Get-Location

try {
    $central = Join-Path $root "central.lhub"
    $ana = Join-Path $root "ana"
    $bia = Join-Path $root "bia"

    Step "Interpretador em uso"
    Write-Host "$py  ($(& $py --version))"

    Step "1) Cria o repositorio central (bare) -- faz o papel da pasta de rede"
    lhub init --bare $central

    Step "2) Ana cria o repo, configura identidade e faz o primeiro commit"
    New-Item -ItemType Directory -Path $ana | Out-Null
    Set-Location $ana
    lhub init
    lhub config user.name "Ana"
    lhub config user.email "ana@exemplo.com"
    "linha 1" | Out-File -Encoding utf8 doc.txt
    lhub add .
    lhub commit -m "primeiro commit (Ana)"
    lhub remote add origin $central
    lhub push origin main

    Step "3) Bia clona o central"
    Set-Location $root
    lhub clone $central $bia
    Set-Location $bia
    lhub config user.name "Bia"
    lhub config user.email "bia@exemplo.com"
    Write-Host "conteudo clonado de doc.txt:" -ForegroundColor DarkGray
    Get-Content doc.txt

    Step "4) Bia edita, commita e envia"
    "linha 1`nlinha 2 (Bia)" | Out-File -Encoding utf8 doc.txt
    lhub add .
    lhub commit -m "Bia adiciona a linha 2"
    lhub push

    Step "5) Ana puxa as mudancas (espera fast-forward)"
    Set-Location $ana
    lhub pull
    Write-Host "doc.txt em Ana apos o pull:" -ForegroundColor DarkGray
    Get-Content doc.txt

    Step "6) Historico final em Ana"
    lhub log --oneline

    Write-Host "`nDEMO OK -- o fluxo init/add/commit/push/clone/pull funcionou." -ForegroundColor Green
}
finally {
    Set-Location $start
    if ($Keep) {
        Write-Host "Pasta de teste mantida em: $root" -ForegroundColor Yellow
    } else {
        Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue
        Write-Host "Pasta de teste removida (use -Keep para manter)." -ForegroundColor DarkGray
    }
}
