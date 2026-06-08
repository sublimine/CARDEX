@echo off
REM Register + start the durable Scheduled Task that runs run_services.cmd (API + delta worker).
schtasks /Create /TN CARDEX-EntityServices /TR "cmd.exe /c C:\Users\elias\projects\cardex-delta\deploy\run_services.cmd" /SC ONLOGON /RL LIMITED /F
schtasks /Run /TN CARDEX-EntityServices
echo INSTALL_TASK_DONE
