# 🖱️ Windows Mouse Gesture Tool
A lightweight and powerful mouse gesture program for Windows built with Python. You can quickly perform tasks such as web browsing navigation, window control, and copy/paste by right-click dragging. It is compatible with all applications in the Windows environment.

# 🚀 Gesture List (Gestures)
Drag while holding down the mouse **Right-Click**.

| Direction | Function | Key Mapping |
| :--- | :--- | :--- |
| → (Right) | Forward | Alt + Right |
| ← (Left) | Back | Alt + Left |
| ↓ (Down) | Paste | Ctrl + V |
| ↑ (Up) | Copy | Ctrl + C |
| ↘ (Down-Right) | Close Tab | Ctrl + W |
| ↖ (Up-Left) | Close Window | Alt + F4 |
| ↗ (Up-Right) | Maximize/Restore | Window Maximize/Restore |
| ↙ (Down-Left) | Minimize | Window Minimize |

# ✨ Key Features
    - Optimization: Uses minimal resources, causing no strain on CPU or memory.
    - Gesture Visualization: A **Magenta Trail** is displayed on the screen when drawing gestures, making it intuitive.
    - No Ghosting/Flickering: Maintains a transparent overlay window to eliminate flickering or ghosting artifacts completely.
    - Tray Icon Support: Check program status and exit via the system tray.
    - Auto-Start Support: Automatically starts on Windows boot without the UAC prompt via install.bat.

# 🛠️ Development Setup
This project is built based on the uv package manager. (pip is also supported)

1. Install Required Libraries
```
# Using uv
uv add pyautogui pygetwindow pystray pillow pyinstaller
```

```
# Using pip
pip install pyautogui pygetwindow pystray pillow pyinstaller
```

2. Run Source Code

```
uv run main.py
```

# 📦 Build EXE
Create a single executable file (.exe) for distribution.
**Note:** Ensure `icon.png` and `MouseGesture.ico` are in the project folder before building.

```
uv run pyinstaller --onefile --noconsole --uac-admin --name "MouseGesture" --icon="MouseGesture.ico" --add-data "icon.png;." main.py
```

--onefile: Compresses into a single file

--noconsole: Hides the black console window

--uac-admin: Automatically requests administrator privileges

--add-data: Includes image for the tray icon


# 💿 Installation & Auto-Start
Users receiving the distribution do not need a separate Python installation.
1. Place `MouseGesture.exe` and `install.bat` in the same folder.
2. Right-click the `install.bat` file and select **[Run as administrator]**.
3. Once configured, it will run automatically on the next boot without a UAC prompt.

- File Structure
```text
MouseGesture/
├── MouseGesture.exe  (Executable Program)
└── install.bat       (Auto-run Registration Script)
```

# ⚠️ Troubleshooting
- No response when running?
    - Check if there is a purple arrow icon in the system tray (next to the clock).
- Auto-start not working?
    - On laptops, Task Scheduler might be blocked in battery mode. install.bat is patched to automatically resolve this, so try running it as administrator again.
- Antivirus Warning
    - Windows Defender may show a warning because it is a personal program (unsigned). Please click [More Info] -> [Run anyway].

# 📝 License
This project is for personal use. Feel free to modify and distribute.
