Option Explicit
Dim fs, shell, root, python, launcher
Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fs.GetParentFolderName(WScript.ScriptFullName)
python = fs.BuildPath(root, "server\.venv\Scripts\pythonw.exe")
launcher = fs.BuildPath(root, "tools\launch_local.py")
If Not fs.FileExists(python) Then
  MsgBox "Python environment is missing. Please follow README setup first.", 48, "Music Core"
Else
  shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & launcher & Chr(34), 0, False
End If
