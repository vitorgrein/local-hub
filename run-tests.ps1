<#
.SYNOPSIS
    Roda a suite de testes do LocalHub no interpretador que voce escolher.

.DESCRIPTION
    Nao precisa instalar o pacote: o script poe a raiz do projeto no PYTHONPATH
    e roda os testes via unittest. Use -Python para escolher o interpretador;
    se omitir, ele detecta automaticamente (py -3 e depois python no PATH).

.PARAMETER Python
    Caminho completo para o python.exe a usar. Se omitido, detecta sozinho.

.EXAMPLE
    .\run-tests.ps1

.EXAMPLE
    .\run-tests.ps1 -Python "C:\caminho\para\python.exe"
#>
[CmdletBinding()]
param([string]$Python)

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
Write-Host "Interpretador: $py" -ForegroundColor Cyan
Write-Host ("Versao: " + (& $py --version))

$env:PYTHONPATH = $here   # acha o pacote 'localhub' sem precisar instalar
& $py -m unittest discover -s (Join-Path $here "tests") -v
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host "`nTodos os testes passaram." -ForegroundColor Green
} else {
    Write-Host "`nHouve falhas nos testes (codigo $code)." -ForegroundColor Red
}
exit $code
