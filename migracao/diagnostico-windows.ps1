<#
  Diagnóstico do computador do cliente, ANTES da migração.

  Ele não copia nada e não muda nada: só olha e conta o que achou. Responde as
  perguntas que decidem se o passo 1 vai funcionar naquela máquina:

    1. Qual é o banco do sistema antigo (Access, Firebird, dBase, SQLite)?
    2. Os arquivos estão em uso, travados pelo sistema antigo?
    3. Tem o driver necessário instalado — e da "bitagem" certa (32 ou 64)?
    4. O Python está instalado?
    5. A internet da loja deixa falar com o banco da nuvem?

  Como rodar (na máquina do cliente):
    - Clique com o botão direito no arquivo > "Executar com o PowerShell"
    - Ou, num PowerShell:
        powershell -ExecutionPolicy Bypass -File diagnostico-windows.ps1 -Pasta "C:\SistemaAntigo" -Destino "host.railway.app:5432"

  No fim ele salva um relatório na Área de Trabalho. Me mande esse arquivo.
#>

param(
    # A pasta onde o sistema antigo está instalado. Em branco, procura nos lugares comuns.
    [string]$Pasta = "",
    # O endereço do banco da nuvem, no formato host:porta. Em branco, pula esse teste.
    [string]$Destino = ""
)

$ErrorActionPreference = "Continue"
$linhas = New-Object System.Collections.ArrayList
function Diga([string]$texto) {
    Write-Host $texto
    [void]$linhas.Add($texto)
}

Diga "============================================================"
Diga " DIAGNOSTICO PRE-MIGRACAO - $(Get-Date -Format 'dd/MM/yyyy HH:mm')"
Diga "============================================================"

# ---------------------------------------------------------------- 1. Windows
Diga ""
Diga "-- O computador --"
try {
    $so = Get-CimInstance Win32_OperatingSystem
    Diga ("  Windows.......: {0} ({1})" -f $so.Caption, $so.OSArchitecture)
} catch { Diga "  Windows.......: nao consegui ler ($($_.Exception.Message))" }
Diga ("  Nome da maquina: {0}" -f $env:COMPUTERNAME)
Diga ("  PowerShell....: {0} ({1})" -f $PSVersionTable.PSVersion, $(if ([Environment]::Is64BitProcess) { "64 bits" } else { "32 bits" }))

# ----------------------------------------------------------------- 2. Python
Diga ""
Diga "-- Python (o sistema novo precisa dele nesta maquina) --"
$achouPython = $false
foreach ($cmd in @("python", "py", "python3")) {
    try {
        $v = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Diga ("  {0,-8} -> {1}" -f $cmd, ($v -join " "))
            $achouPython = $true
        }
    } catch { }
}
if (-not $achouPython) { Diga "  NAO ENCONTRADO - vai precisar instalar o Python 3.12 ou mais novo" }

# ------------------------------------------------------- 3. Arquivos de dados
Diga ""
Diga "-- Onde estao os dados do sistema antigo --"
$extensoes = @("*.mdb", "*.accdb", "*.fdb", "*.gdb", "*.dbf", "*.db", "*.sqlite", "*.sqlite3")
$locais = @()
if ($Pasta -ne "") {
    $locais += $Pasta
} else {
    Diga "  (nenhuma pasta informada; procurando nos lugares comuns)"
    $locais += @("C:\", "C:\Program Files", "C:\Program Files (x86)", "C:\Users\Public", "$env:USERPROFILE\Desktop", "$env:USERPROFILE\Documents")
}

$encontrados = @()
foreach ($local in $locais) {
    if (-not (Test-Path $local)) { continue }
    # Profundidade limitada: varrer o disco inteiro demora demais numa maquina de loja.
    $profundidade = if ($local -eq "C:\") { 2 } else { 4 }
    try {
        $achados = Get-ChildItem -Path $local -Include $extensoes -Recurse -Depth $profundidade -File -ErrorAction SilentlyContinue |
                   Where-Object { $_.Length -gt 0 } | Select-Object -First 60
        $encontrados += $achados
    } catch { }
}

if ($encontrados.Count -eq 0) {
    Diga "  Nenhum arquivo de banco encontrado."
    Diga "  Rode de novo apontando a pasta do sistema antigo:"
    Diga "     .\diagnostico-windows.ps1 -Pasta ""C:\Caminho\Do\Sistema"""
} else {
    foreach ($arquivo in ($encontrados | Sort-Object Length -Descending | Select-Object -First 25)) {
        # Um arquivo aberto pelo sistema antigo nao deixa abrir pra escrita.
        $emUso = "livre"
        try {
            $fs = [System.IO.File]::Open($arquivo.FullName, 'Open', 'Read', 'None')
            $fs.Close()
        } catch { $emUso = "EM USO (sistema antigo aberto?)" }
        Diga ("  {0,-10} {1,10:N0} KB  {2}  [{3}]" -f $arquivo.Extension, ($arquivo.Length / 1KB), $arquivo.FullName, $emUso)
    }
    Diga ""
    $porTipo = $encontrados | Group-Object Extension | Sort-Object Count -Descending
    Diga ("  Resumo: " + (($porTipo | ForEach-Object { "$($_.Count)x $($_.Name)" }) -join ", "))
}

# ------------------------------------------------------------- 4. Drivers ODBC
Diga ""
Diga "-- Drivers instalados (Access e companhia) --"
try {
    $drivers = Get-OdbcDriver -ErrorAction Stop
    $interessantes = $drivers | Where-Object { $_.Name -match "Access|dBASE|SQL Server|MySQL|Firebird|Text" }
    if ($interessantes) {
        foreach ($d in $interessantes) { Diga ("  [{0,-6}] {1}" -f $d.Platform, $d.Name) }
    } else {
        Diga "  Nenhum driver de Access/dBASE/SQL Server encontrado."
    }
    Diga ""
    Diga "  ATENCAO: a bitagem do driver tem que bater com a do Python."
    Diga "  Driver 32-bit + Python 64-bit = 'data source name not found'. E o erro mais comum."
} catch {
    Diga "  Nao consegui listar os drivers ODBC ($($_.Exception.Message))"
}

# --------------------------------------------------------------- 5. Firebird
Diga ""
Diga "-- Firebird (se o sistema antigo for .fdb/.gdb) --"
$fb = @()
foreach ($caminho in @("C:\Windows\System32\fbclient.dll", "C:\Windows\SysWOW64\fbclient.dll",
                       "C:\Program Files\Firebird", "C:\Program Files (x86)\Firebird")) {
    if (Test-Path $caminho) { $fb += $caminho }
}
if ($fb.Count -gt 0) { foreach ($f in $fb) { Diga "  encontrado: $f" } } else { Diga "  Nao encontrado (so importa se o banco for Firebird)" }
try {
    $servico = Get-Service -Name "Firebird*" -ErrorAction SilentlyContinue
    if ($servico) { foreach ($s in $servico) { Diga ("  servico: {0} = {1}" -f $s.Name, $s.Status) } }
} catch { }

# ------------------------------------------------------- 6. Chegar na nuvem
Diga ""
Diga "-- A internet da loja deixa falar com o banco da nuvem? --"
if ($Destino -eq "") {
    Diga "  (nenhum destino informado; rode com -Destino ""host:porta"" pra testar)"
} else {
    $partes = $Destino.Split(":")
    $host_ = $partes[0]
    $porta = if ($partes.Count -gt 1) { [int]$partes[1] } else { 5432 }
    try {
        $teste = Test-NetConnection -ComputerName $host_ -Port $porta -WarningAction SilentlyContinue
        if ($teste.TcpTestSucceeded) {
            Diga ("  OK: consegue chegar em {0}:{1}" -f $host_, $porta)
        } else {
            Diga ("  BLOQUEADO: nao chega em {0}:{1}" -f $host_, $porta)
            Diga "  Costuma ser firewall ou antivirus da loja bloqueando porta de saida."
        }
    } catch {
        Diga ("  Falhou o teste de conexao: {0}" -f $_.Exception.Message)
    }
}

# ------------------------------------------------------------------ relatorio
$destinoArquivo = Join-Path ([Environment]::GetFolderPath("Desktop")) "diagnostico-migracao.txt"
try {
    $linhas | Out-File -FilePath $destinoArquivo -Encoding UTF8
    Diga ""
    Diga "============================================================"
    Diga " Relatorio salvo em: $destinoArquivo"
    Diga " Mande este arquivo para quem esta fazendo a migracao."
    Diga "============================================================"
} catch {
    Diga "Nao consegui salvar o relatorio: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Pressione Enter para fechar..."
Read-Host | Out-Null
