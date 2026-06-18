<#
.SYNOPSIS
    Instala o LocalHub (comando `lhub`) no interpretador Python que voce escolher.

.DESCRIPTION
    Cada pessoa aponta para o SEU python.exe. O script valida o interpretador,
    instala o pacote a partir desta pasta (ou de um wheel) e, opcionalmente,
    adiciona a pasta Scripts ao PATH do usuario para o comando `lhub` ficar
    disponivel em qualquer terminal. Ao final, confere com `lhub --version`.

.PARAMETER Python
    Caminho completo para o python.exe a usar. Se omitido, o script tenta
    detectar automaticamente (py -3 e depois python no PATH).

.PARAMETER Editable
    Instala em modo editavel (pip install -e .) -- recomendado para desenvolver
    a partir do codigo desta pasta.

.PARAMETER FromWheel
    Instala a partir de um arquivo .whl (informe o caminho), em vez desta pasta.

.PARAMETER AddToPath
    Adiciona a pasta Scripts do interpretador ao PATH do usuario (permanente).

.EXAMPLE
    .\install.ps1 -Python "C:\caminho\para\python.exe" -AddToPath

.EXAMPLE
    .\install.ps1                      # detecta o Python automaticamente

.EXAMPLE
    .\install.ps1 -FromWheel "\\servidor\share\dist\localhub-0.1.0-py3-none-any.whl" -AddToPath
#>
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Editable,
    [string]$FromWheel,
    [switch]$AddToPath
)

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
    throw "Nenhum Python encontrado. Informe -Python 'C:\caminho\para\python.exe' (veja com 'py -0p')."
}

$py = Resolve-Python -Path $Python
Write-Host "Interpretador: $py" -ForegroundColor Cyan
Write-Host ("Versao: " + (& $py --version))

# --- instalacao ---
if ($FromWheel) {
    if (-not (Test-Path $FromWheel)) { throw "Wheel nao encontrado: $FromWheel" }
    Write-Host "Instalando a partir do wheel: $FromWheel"
    & $py -m pip install $FromWheel
} elseif ($Editable) {
    Write-Host "Instalando em modo editavel a partir de: $here"
    & $py -m pip install -e $here
} else {
    Write-Host "Instalando a partir de: $here"
    & $py -m pip install $here
}
if ($LASTEXITCODE -ne 0) { throw "pip install falhou (codigo $LASTEXITCODE)" }

# --- onde ficou o comando ---
$scripts = (& $py -c "import sysconfig; print(sysconfig.get_path('scripts'))").Trim()
$lhub = Join-Path $scripts "lhub.exe"
Write-Host "Comando instalado: $lhub" -ForegroundColor Green

# --- PATH (opcional) ---
if ($AddToPath) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$scripts*") {
        [Environment]::SetEnvironmentVariable("Path", ("$userPath;$scripts").Trim(";"), "User")
        Write-Host "Adicionado ao PATH do usuario: $scripts" -ForegroundColor Yellow
        Write-Host "Reabra o terminal para o novo PATH valer." -ForegroundColor Yellow
    } else {
        Write-Host "Ja estava no PATH do usuario."
    }
}

# --- verificacao ---
Write-Host "Conferindo a instalacao..." -ForegroundColor Cyan
& $lhub --version
