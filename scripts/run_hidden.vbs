' Wrapper generico p/ Agendador de Tarefas: roda o .cmd passado como arg
' sem abrir janela de console. wscript.exe nao tem janela propria; o
' WindowStyle 0 no shell.Run suprime a janela do cmd/python filho tambem.
' Uso (Task To Run do schtasks):
'   wscript.exe //B "<projeto>\scripts\run_hidden.vbs" "<projeto>\scripts\publish_short.cmd"
Set args = WScript.Arguments
Set shell = CreateObject("WScript.Shell")
shell.Run """" & args(0) & """", 0, True
