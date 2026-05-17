!macro KillInterviewAgentProcesses
  nsExec::ExecToLog 'taskkill /F /T /IM ai-agent-interview-coach.exe'
  nsExec::ExecToLog 'taskkill /F /T /IM interview-agent-sidecar.exe'
  Sleep 500
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro KillInterviewAgentProcesses
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro KillInterviewAgentProcesses
!macroend
