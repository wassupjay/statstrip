' Launches collector + display, windowless.
' install.bat passes resolved absolute paths as arguments (collector.exe,
' display.exe, pythonw.exe), immune to PATH problems at login. Run with no
' arguments (manual use), it falls back to PATH lookups. If nothing can be
' launched, says so instead of failing silently.
Set shell = CreateObject("WScript.Shell")

Function Q(s)
    Q = Chr(34) & s & Chr(34)
End Function

Function RunFirst(cmds)
    Dim i
    RunFirst = False
    For i = 0 To UBound(cmds)
        On Error Resume Next
        Err.Clear
        shell.Run cmds(i), 0, False
        If Err.Number = 0 Then
            RunFirst = True
            Exit Function
        End If
        On Error GoTo 0
    Next
End Function

If WScript.Arguments.Count >= 3 Then
    pyw = Q(WScript.Arguments(2))
    collectorCmds = Array(Q(WScript.Arguments(0)), pyw & " -m statstrip.collector")
    displayCmds = Array(Q(WScript.Arguments(1)), pyw & " -m statstrip.display")
Else
    collectorCmds = Array("statstrip-collector.exe", "pythonw -m statstrip.collector")
    displayCmds = Array("statstrip-display.exe", "pythonw -m statstrip.display")
End If

okCollector = RunFirst(collectorCmds)
WScript.Sleep 1500
okDisplay = RunFirst(displayCmds)

If Not (okCollector And okDisplay) Then
    MsgBox "StatStrip could not launch (collector/display executables not found)." _
        & vbCrLf & "Re-run install.bat to repair the installation.", _
        vbExclamation, "StatStrip"
End If
