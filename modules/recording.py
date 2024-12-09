import pyautogui


def start():
    # Alt + F9 キーを押して録画を開始
    pyautogui.hotkey("alt", "f9")
    print("Recording started...")


def stop():
    # Alt + F9 キーを押して録画を停止
    pyautogui.hotkey("alt", "f9")
    print("Recording stopped...")
