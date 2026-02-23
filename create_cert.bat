@echo off
echo ===================================================
echo Windows Runtime Host Certificate Generator (Self-Signed)
echo ===================================================

cd "%~dp0"
echo Creating certificate in: %CD%

echo [INFO] Generating certificate for: mjulez70
powershell -Command "$cert = New-SelfSignedCertificate -Subject 'CN=mjulez70' -Type CodeSigningCert -CertStoreLocation 'Cert:\CurrentUser\My'; $Password = ConvertTo-SecureString -String '1234' -Force -AsPlainText; Export-PfxCertificate -Cert $cert -FilePath 'windows-runtime-host.pfx' -Password $Password"

if exist "windows-runtime-host.pfx" (
    echo.
    echo [SUCCESS] windows-runtime-host.pfx has been generated!
    echo The password for the certificate is: 1234
    echo Keep this file secure.
) else (
    echo.
    echo [ERROR] Failed to generate certificate.
)
