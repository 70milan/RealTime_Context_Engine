# WinHostSvc.py - Windows Service wrapper for the backend
# This makes the app appear in Services instead of Processes in Task Manager

import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os
import threading
import uvicorn

# Add the backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app

class WindowsHostService(win32serviceutil.ServiceFramework):
    _svc_name_ = "WinHostSvc"
    _svc_display_name_ = "Windows Runtime Host Service"
    _svc_description_ = "Interview Assistant - Windows Runtime Host Support"

    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server = None
        self.thread = None
        
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.server:
            self.server.should_exit = True
            
    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()
        
    def main(self):
        config = uvicorn.Config(app, host="127.0.0.1", port=5050, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run)
        self.thread.start()
        
        # Wait for stop signal
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        
        if self.server:
            self.server.should_exit = True
            self.thread.join(timeout=5)

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(WindowsHostService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(WindowsHostService)
