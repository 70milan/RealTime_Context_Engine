-- front
npm run start:dev
# or
npm run electron 

-- back
uvicorn main:app --reload --host 127.0.0.1 --port 5050 


taskkill /F /IM jobandit.exe /IM interview-backend.exe 2>$null


pyinstaller --onefile --name interview-backend main.py

Unpersist license key
open console control shift I
localStorage.removeItem('valid_license_key');
