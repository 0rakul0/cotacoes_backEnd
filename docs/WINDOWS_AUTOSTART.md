# FastAPI do Cotações iniciado automaticamente no Windows

Para manter o backend funcionando **depois de fechar o terminal e após reiniciar o computador**, utilizamos o Agendador de Tarefas nativo do Windows. Não é necessário NSSM, Docker ou deixar o PyCharm aberto.

> A tarefa roda como seu usuário Windows (não como SYSTEM). Será solicitada sua **senha real da conta**, porque um PIN do Windows Hello não funciona para registrar um processo executado antes de entrar no Windows. Não coloque a senha no script ou repositório.

## 1. Prepare o ambiente virtual

No PowerShell, dentro da pasta `cotacoes_backEnd`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 7777
```

Depois de testar `http://127.0.0.1:7777/api/health`, interrompa o processo de teste com Ctrl+C.

Caso `py -3.12` não esteja instalado, utilize `py -m venv .venv` com uma versão de Python compatível (3.10+).

## 2. Instale a tarefa de inicialização

Abra **PowerShell como Administrador**, entre no repositório e execute:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\install_cotacoes_task.ps1
```

O script faz o seguinte:
- Registra `Cotacoes-FastAPI` com disparo **Ao iniciar o computador**.
- Executa `scripts/windows/start_cotacoes.cmd` sob sua conta Windows.
- Configura reinício automático após falhas, com intervalo de 1 minuto e limite de 999 tentativas.
- Não interrompe a tarefa após um limite padrão de horas/dias.
- Trabalha sempre no diretório correto, usando `.venv\Scripts\python.exe`.
- Grava logs em `data\logs\cotacoes-windows.log`.
- Mantém `127.0.0.1:7777`: o serviço é acessível somente no próprio computador.

A tarefa não precisa da sua sessão aberta, **desde que o Windows esteja ligado e não esteja em suspensão**. Para funcionamento permanente, configure as opções de energia do Windows para não suspender o PC enquanto o servidor precisar ficar ativo.

## 3. Verifique e gerencie

```powershell
Get-ScheduledTask -TaskName "Cotacoes-FastAPI"
Get-ScheduledTaskInfo -TaskName "Cotacoes-FastAPI"
Invoke-RestMethod http://127.0.0.1:7777/api/health
Get-Content .\data\logs\cotacoes-windows.log -Tail 40
```

Reiniciar:

```powershell
Stop-ScheduledTask -TaskName "Cotacoes-FastAPI"
Start-ScheduledTask -TaskName "Cotacoes-FastAPI"
```

Desinstalar sem apagar dados:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\remove_cotacoes_task.ps1
```

## Solução manual pelo Agendador de Tarefas

Abra `taskschd.msc` > **Criar Tarefa**:
1. Geral: escolha sua conta Windows e marque **Executar estando o usuário conectado ou não**.
2. Disparadores: **Ao iniciar**.
3. Ações: **Iniciar um programa**, selecione `scripts\windows\start_cotacoes.cmd` pelo caminho absoluto.
4. Configurações: selecione **Se a tarefa falhar, reiniciar a cada 1 minuto** e **Se a tarefa já estiver em execução, não iniciar uma nova instância**.
5. Desative **Parar a tarefa se ela for executada por mais de 3 dias**.
6. Salve informando a senha da sua conta Windows; clique em **Executar** para testar.

## Segurança e limites

O backend atual permite manipulação de carteira e dados locais. **Não exponha a porta 7777 à Internet**. O launcher usa 127.0.0.1 por segurança. Para acessar de outros dispositivos, configure autenticação, firewall, TLS/reverse proxy e uma conta de serviço com permissões restritas.

O processo rodará enquanto o Windows estiver ligado. Desligamento, suspensão, ausência de conexão com o provedor de cotações ou bloqueio pela política de rede interrompem as respectivas funcionalidades. O Agendador reinicia o backend após o próximo boot.
