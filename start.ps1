# Kemo LLM Adapter — Windows (PowerShell) 启动脚本
param(
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 加载 provider 密钥
if (Test-Path provider.env) {
    Get-Content provider.env | ForEach {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim())
        }
    }
    Write-Host "[kemo] loaded provider.env"
}

# 创建运行数据目录
New-Item -ItemType Directory -Force -Path data_status/call_log | Out-Null

Write-Host "[kemo] starting server..."
python server.py @Args
