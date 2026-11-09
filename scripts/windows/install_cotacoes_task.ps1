#requires -Version 5.1
<#
.SYNOPSIS
Registra o backend Cotacoes para iniciar junto com o Windows.
.DESCRIPTION
Cria tarefa agendada "Ao iniciar", usando as credenciais do proprio usuario,
sem rodar a API com privilegios de SYSTEM. Nao altera politicas globais.
Requer PowerShell elevado e a senha real do Windows (nao PIN).
#>
[CmdletBinding()]
param(
    [string]$TaskName = "Cotacoes-FastAPI"
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)) {
    throw "Agendador de Tarefas nao disponivel neste Windows."
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$windowsPrincipal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $windowsPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Abra o PowerShell como Administrador e execute novamente."
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
$runner = Join-Path $PSScriptRoot "start_cotacoes.cmd"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Ambiente virtual nao encontrado. Crie .venv e instale requirements.txt primeiro: $python"
}
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Launcher nao encontrado: $runner"
}

Write-Host "Servidor local: http://127.0.0.1:7777" -ForegroundColor Cyan
Write-Host "A tarefa vai iniciar ao ligar o Windows, mesmo sem login."
Write-Host "Informe o usuario e a SENHA do Windows (nao a senha do GitHub, nem PIN)."
$credential = Get-Credential -UserName $identity.Name -Message "Conta Windows para executar o servidor em segundo plano"
if (-not $credential) { throw "Operacao cancelada." }
$user = $credential.UserName
$password = $credential.GetNetworkCredential().Password
if ([string]::IsNullOrWhiteSpace($password)) {
    throw "A tarefa de inicio automatico requer senha de conta Windows."
}

$cmd = Join-Path $env:WINDIR "System32\cmd.exe"
$arguments = '/d /c ""' + $runner + '""'
$action = New-ScheduledTaskAction -Execute $cmd -Argument $arguments -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 999 `
    -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

try {
    Register-ScheduledTask -TaskName $TaskName `
        -Description "FastAPI Cotacoes local; reiniciar automaticamente em caso de falha." `
        -Action $action -Trigger $trigger -Settings $settings `
        -User $user -Password $password -Force | Out-Null
} finally {
    $password = $null
    $credential = $null
}
Start-ScheduledTask -TaskName $TaskName
Write-Host "Tarefa instalada e iniciada: $TaskName" -ForegroundColor Green
Write-Host "Verifique: Invoke-RestMethod http://127.0.0.1:7777/api/health"
Write-Host "Logs: $repo\data\logs\cotacoes-windows.log"
Write-Host "Para parar: Stop-ScheduledTask -TaskName '$TaskName'"
Write-Host "Para iniciar: Start-ScheduledTask -TaskName '$TaskName'"
