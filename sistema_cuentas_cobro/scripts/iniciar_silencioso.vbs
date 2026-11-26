Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ProjectDir = FSO.GetParentFolderName(FSO.GetParentFolderName(WScript.ScriptFullName))
WshShell.CurrentDirectory = ProjectDir
WshShell.Run "pythonw.exe """ & ProjectDir & "\launcher.py""", 0, False
