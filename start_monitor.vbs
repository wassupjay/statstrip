' Launches collector + display, windowless.
' Prefers the pip-installed statstrip-*.exe entry points; falls back to
' "pythonw -m ..." when the pip Scripts dir isn't on PATH (common for
' per-user installs).
Set shell = CreateObject("WScript.Shell")

Sub RunFirst(cmds)
    Dim i
    For i = 0 To UBound(cmds)
        On Error Resume Next
        Err.Clear
        shell.Run cmds(i), 0, False
        If Err.Number = 0 Then Exit Sub
        On Error GoTo 0
    Next
End Sub

RunFirst Array("statstrip-collector.exe", "pythonw -m statstrip.collector")
WScript.Sleep 1500
RunFirst Array("statstrip-display.exe", "pythonw -m statstrip.display")
