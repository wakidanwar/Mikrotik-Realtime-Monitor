' Run MikroTik monitor without a console window.
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = base
pythonw = base & "\.venv\Scripts\pythonw.exe"
script = base & "\main.py"
If Not fso.FileExists(pythonw) Then
    MsgBox "Virtual environment not found. Create it first:" & vbCrLf & _
           "python -m venv .venv" & vbCrLf & _
           ".venv\Scripts\python.exe -m pip install -r requirements.txt", _
           vbExclamation, "MikroTik Monitor"
    WScript.Quit 1
End If
' Pass through any arguments.
args = ""
For i = 0 To WScript.Arguments.Count - 1
    args = args & " " & Chr(34) & WScript.Arguments(i) & Chr(34)
Next
WshShell.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & script & Chr(34) & args, 0, False
