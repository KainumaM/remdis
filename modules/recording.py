import pyautogui
import pygetwindow as gw

# Alt + F9 キーを押して録画を開始
def start():
    activate_obs_window()
    pyautogui.hotkey("alt", "f9")
    print("Recording started...")

# Alt + F9 キーを押して録画を停止
def stop():
    activate_obs_window()
    pyautogui.hotkey("alt", "f9")
    print("Recording stopped...")

# （laptop用）OBS をアクティブにする
def activate_obs_window():
    obs_window = None
    for window in gw.getAllTitles():
        if "OBS" in window:
            obs_window = gw.getWindowsWithTitle(window)[0]
            break
    if obs_window:
        obs_window.activate()
    else:
        print("OBS のウィンドウが見つかりません。")
