"""Keys and passwords (Hugging Face, monday) are kept in the operating system's own encrypted store
(Windows Credential Manager / macOS Keychain) - never in a text file, never pasted into the chat.

Usage:
    python scripts/secrets_store.py set NAME     # opens a small window with a text box, paste with Ctrl+V
    python scripts/secrets_store.py check NAME   # prints OK and the length, never the value
    python scripts/secrets_store.py delete NAME

Note for Hebrew keyboards: Ctrl+V in the window works only when the keyboard is switched to English
(Alt+Shift). In Hebrew the paste silently does nothing.
"""
import sys

import keyring

SERVICE = "recordings-kit"


def set_gui(name: str) -> None:
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    value = simpledialog.askstring(
        "Recordings kit", f"Paste {name} here (Ctrl+V, keyboard in English) and press OK", show="*", parent=root)
    if value and value.strip():
        keyring.set_password(SERVICE, name, value.strip())
        messagebox.showinfo("Recordings kit", f"Saved ({len(value.strip())} characters). You can close this.", parent=root)
        print(f"OK {name} saved (length={len(value.strip())})")
    else:
        print("ERR nothing saved")


def main() -> None:
    cmd, name = sys.argv[1], sys.argv[2]
    if cmd == "set":
        set_gui(name)
    elif cmd == "check":
        value = keyring.get_password(SERVICE, name)
        print(f"OK {name} length={len(value)}" if value else f"MISSING {name}")
    elif cmd == "delete":
        keyring.delete_password(SERVICE, name)
        print(f"OK {name} deleted")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
