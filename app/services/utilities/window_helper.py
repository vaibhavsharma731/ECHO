import sys

def get_active_window_title() -> str:
    """
    Finds the title of the window the user is currently looking at.
    This is like checking which notebook or app the user has open on their desk.
    """
    # Since we are on Windows, we can use win32gui (via pywin32) which is very reliable.
    if sys.platform == 'win32':
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            return title if title else "Desktop"
        except Exception:
            pass
            
    # Fallback to pygetwindow if win32gui fails or on non-Windows (for future support)
    try:
        import pygetwindow as gw
        win = gw.getActiveWindow()
        if win is not None and win.title:
            return win.title
    except Exception:
        pass
        
    return "Unknown"
