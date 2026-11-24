# Overnight watchdog: keep PC awake, restart generate_lsb_v10.py if it dies, stop at 10 complete models.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
$Progress = Join-Path $Root "results\progress.json"
$Python = Join-Path $Root "venv\Scripts\python.exe"
$Runner = Join-Path $Root "generate_lsb_v10.py"
$Log = Join-Path $LogDir "watchdog.log"
$Need = @(
    "quiz50", "safety50", "code", "cwe50", "bax50",
    "llmseceval", "cybersec", "cweval", "baxbench", "multi_turn", "repo"
)
$Target = 10

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Watch([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $Log -Value $line
    Write-Host $line
}

try {
    $sig = @"
[DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
"@
    $ste = Add-Type -MemberDefinition $sig -Name NativeSleep -Namespace Win32 -PassThru
    [void]$ste::SetThreadExecutionState([uint32]2147483651)
    Write-Watch "keep-awake enabled"
} catch {
    Write-Watch "keep-awake failed: $_"
}

function Get-CompleteCount {
    if (-not (Test-Path $Progress)) { return 0 }
    try {
        $json = Get-Content -Raw -Path $Progress | ConvertFrom-Json
    } catch {
        return 0
    }
    $n = 0
    foreach ($model in @($json.models)) {
        $suites = @($model.completed_suites)
        $ok = $true
        foreach ($name in $Need) {
            if ($suites -notcontains $name) { $ok = $false; break }
        }
        $err = [string]$model.error
        if ($ok -and [string]::IsNullOrWhiteSpace($err)) { $n++ }
    }
    return $n
}

function Get-Runner {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -match 'generate_lsb_v10\.py' }
}

Write-Watch "watchdog start root=$Root"
while ($true) {
    $done = Get-CompleteCount
    $alive = @(Get-Runner)
    Write-Watch "complete=$done/$Target runner_procs=$($alive.Count)"
    if ($done -ge $Target) {
        Write-Watch "all $Target models complete; exiting"
        break
    }
    if ($alive.Count -eq 0) {
        Write-Watch "runner missing; starting generate_lsb_v10.py"
        Start-Process -FilePath $Python -ArgumentList "`"$Runner`"" -WorkingDirectory $Root -WindowStyle Hidden
        Start-Sleep -Seconds 20
    }
    Start-Sleep -Seconds 90
}
Write-Watch "watchdog done"
