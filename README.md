# 🔥 StayActive

**StayActive** is a cross-platform, next-generation “stealth” presence-keeper app with a beautiful modern UI and full multilingual support (English/Japanese).  
It keeps your computer always “active” (never idle), prevents sleep/screensaver/auto-away—**without ever moving your mouse cursor or interfering with your work**.

---

## 🚀 Features

- **Stealth Mode:** Keeps your status online, disables sleep/screensaver, 100% undetectable (Windows/macOS/Linux supported).
- **Multi-language:** Full English & Japanese UI (switch any time).
- **Modern UX:** Gorgeous, intuitive, high-DPI ready, dark/light theme friendly.
- **Normal Mode:** (Fallback) Tiny invisible cursor wiggle for legacy or locked-down systems.
- **No Admin Needed:** Works as a standard user on almost any OS.
- **Open Source:** Free to use, safe, MIT license.

---

## 🖥 Supported Platforms

- **Windows 10/11:** Full Stealth Mode.
- **macOS:** Stealth via `caffeinate`.
- **Linux:** Stealth via `xdg-screensaver` or `xdotool` (auto-detected).
    - If unavailable, Normal (cursor move) mode works.

---

## 📝 Installation

### 1. Install Python

- Python 3.10+ recommended ([Download Python](https://www.python.org/downloads/))

### 2. Install Dependencies

```bash
pip install pyqt6 pyautogui keyboard
# On Linux for full stealth mode:
sudo apt install xdotool xdg-utils
# On macOS: caffeinate is included by default
````

### 3. Run the App

```bash
python main.py
```

---

## 🟦 Usage

* **Default language:** English (change anytime in UI)
* **Default mode:** Stealth (No Interference)
* **Enable:** Click “Stay Active Now” (checkbox)
* **Minimize:** “Minimize” button (centered)
* **Quit:** “Exit” button (centered)
* **Hotkey:** `Ctrl+Alt+J` (toggle ON/OFF from anywhere)

If your OS doesn’t support stealth, only “Visible Jiggle” mode will be available.

---

## 🌐 Language Switching

Use the dropdown at the bottom to instantly switch UI between English and Japanese.

---

## 💡 FAQ

### Q: Stealth mode is greyed out or unavailable?

* On Linux, install `xdotool` or `xdg-screensaver`.
* On macOS, `caffeinate` (built-in) is used.
* In some restricted corporate environments, only normal mode may be available.

### Q: Can I customize, redistribute, or rebrand StayActive?

* Yes! 100% open source (MIT License).
* Add your logo/branding if you wish.

---

## 🛠️ For Developers

* Easy to localize—just add your language to the `I18N` dictionary in the code.
* All UI strings are externalized for translation.
* Stealth logic is modular/extensible.

---

## 📝 License

MIT License.

---

## 🏆 Credits

* Developed by TomonariWorks
