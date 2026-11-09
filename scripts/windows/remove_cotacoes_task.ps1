#requires -Version 5.1
<#
.SYNOPSIS
Para e remove apenas a tarefa Cotacoes; preserva banco, codigo e logs.
#>
[CmdletBinding()]
param([string]$TaskName = "Cotacoes-FastAPI")

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Tarefa nao encontrada: $TaskName"
    exit 0
}
if ($task.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Tarefa removida. Banco SQLite, logs e modelos permanecem intactos."
