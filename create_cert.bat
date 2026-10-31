@echo off
echo ===================================================
echo Windows Runtime Host Certificate Generator (Self-Signed)
echo ===================================================
echo.
echo Creates a new code-signing cert (CN=mjulez70, RSA 3072, 3 years) with a random
echo password. Outputs:
echo   windows-runtime-host.pfx            (repo root, gitignored - used by the build)
echo   %%USERPROFILE%%\.signing\               (backup .pfx, public .cer, password file)
echo and sets the CSC_KEY_PASSWORD user environment variable.
echo.
echo AFTER RUNNING: put the printed thumbprint in frontend\update-signature.js
echo (TRUSTED_SIGNER_THUMBPRINTS) or the app will reject updates signed with it.
echo Ship a release that trusts BOTH thumbprints before switching the build over.
echo.

cd "%~dp0"
if exist "windows-runtime-host.pfx" (
    echo [ERROR] windows-runtime-host.pfx already exists. Move it into %%USERPROFILE%%\.signing\retired first.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$vault = Join-Path $env:USERPROFILE '.signing'; New-Item -ItemType Directory -Force $vault | Out-Null;" ^
  "$chars = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';" ^
  "$bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes);" ^
  "$pw = -join ($bytes | ForEach-Object { $chars[$_ %% $chars.Length] });" ^
  "$cert = New-SelfSignedCertificate -Subject 'CN=mjulez70' -Type CodeSigningCert -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 -KeyExportPolicy Exportable -NotAfter (Get-Date).AddYears(3) -CertStoreLocation 'Cert:\CurrentUser\My';" ^
  "Export-PfxCertificate -Cert $cert -FilePath 'windows-runtime-host.pfx' -Password (ConvertTo-SecureString $pw -Force -AsPlainText) | Out-Null;" ^
  "Copy-Item 'windows-runtime-host.pfx' (Join-Path $vault 'windows-runtime-host.pfx') -Force;" ^
  "Export-Certificate -Cert $cert -FilePath (Join-Path $vault 'windows-runtime-host.cer') | Out-Null;" ^
  "Set-Content -Path (Join-Path $vault 'windows-runtime-host.pfx.password.txt') -Value $pw -Encoding ascii -NoNewline;" ^
  "[Environment]::SetEnvironmentVariable('CSC_KEY_PASSWORD', $pw, 'User');" ^
  "Write-Host ('[SUCCESS] Thumbprint: ' + $cert.Thumbprint);" ^
  "Write-Host ('Password saved to ' + (Join-Path $vault 'windows-runtime-host.pfx.password.txt') + ' and CSC_KEY_PASSWORD (open a new terminal).')"

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to generate certificate.
)
pause
