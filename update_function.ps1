# PowerShell script for Windows deployment
# Usage: .\update_function.ps1 <environment> [additional-args]
# Example: .\update_function.ps1 dev

param(
    [Parameter(Mandatory=$true)]
    [string]$Environment,
    
    [Parameter(Mandatory=$false)]
    [string]$AdditionalArgs = ""
)

# Remove existing zip file if it exists
if (Test-Path "deploy_functions.zip") {
    Remove-Item "deploy_functions.zip" -Force
    Write-Host "Removed existing deploy_functions.zip" -ForegroundColor Yellow
}

# Create zip file excluding __pycache__ and .git files
Write-Host "Creating deployment package..." -ForegroundColor Cyan

# Get all files recursively, excluding __pycache__ and .git directories
$files = Get-ChildItem -Path . -Recurse -File | Where-Object {
    $_.FullName -notmatch '__pycache__' -and 
    $_.FullName -notmatch '\.git'
}

Write-Host "Found $($files.Count) files to package" -ForegroundColor Gray

# Create zip file using .NET compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$compressionLevel = [System.IO.Compression.CompressionLevel]::Optimal
$zipFile = [System.IO.Compression.ZipFile]::Open("$PWD\deploy_functions.zip", 'Create')

$fileCount = 0
foreach ($file in $files) {
    $relativePath = $file.FullName.Substring($PWD.Path.Length + 1)
    try {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zipFile, $file.FullName, $relativePath, $compressionLevel) | Out-Null
        $fileCount++
        if ($fileCount % 100 -eq 0) {
            Write-Host "  Packaged $fileCount files..." -ForegroundColor Gray
        }
    }
    catch {
        Write-Warning "Could not add $relativePath to zip: $_"
    }
}

$zipFile.Dispose()
Write-Host "[SUCCESS] Deployment package created successfully ($fileCount files)" -ForegroundColor Green

# Deploy to AWS Lambda
$functionName = "$Environment-GEPPPlatform"
Write-Host ""
Write-Host "DEPLOYING to $functionName..." -ForegroundColor Cyan

try {
    if ($AdditionalArgs) {
        $output = aws lambda update-function-code --function-name $functionName --zip-file fileb://deploy_functions.zip $AdditionalArgs.Split(' ') 2>&1
    }
    else {
        $output = aws lambda update-function-code --function-name $functionName --zip-file fileb://deploy_functions.zip 2>&1
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[SUCCESS] Deployment successful!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Function: $functionName" -ForegroundColor White
    }
    else {
        Write-Host "[FAILED] Deployment failed with exit code $LASTEXITCODE" -ForegroundColor Red
        Write-Host $output -ForegroundColor Red
    }
}
catch {
    Write-Host "[ERROR] Error during deployment: $_" -ForegroundColor Red
}

# Uncommented sections from original script (for reference):
# To install Python packages:
# pip install `
# --platform manylinux2014_x86_64 `
# --target=./ `
# --implementation cp `
# --python-version 3.9 `
# --only-binary=:all: --upgrade `
# squarify

