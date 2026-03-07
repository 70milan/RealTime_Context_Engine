Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile('C:\Users\milan\.gemini\antigravity\brain\9f6acc06-3f2c-4b51-ad63-c4ed0dbc02d7\architecture_diagram_1772856157817.png')
$img.Save('C:\Data Engineering\release_package\architecture_diagram.jpg', [System.Drawing.Imaging.ImageFormat]::Jpeg)
$img.Dispose()
