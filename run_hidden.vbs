Option Explicit

Dim fso, shell, baseDir, launcher, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = fso.BuildPath(baseDir, "02_launch.bat")
command = Chr(34) & launcher & Chr(34)

' Window style 0 keeps the console hidden; 02_launch.bat still writes logs.
shell.Run command, 0, False

