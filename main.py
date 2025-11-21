import sys
import ctypes
import time
import threading
import pyautogui
import pygetwindow as gw
import tkinter as tk
import math  # 거리 계산을 위해 추가
from ctypes import wintypes, byref

# --- 0. 관리자 권한 강제 실행 ---
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, ' '.join([f'"{arg}"' for arg in sys.argv]), None, 1
    )
    sys.exit()

# --- 1. 설정 및 최적화 ---
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False

# --- 2. WinAPI 및 상수 정의 ---
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
PM_REMOVE = 0x0001
LLMHF_INJECTED = 0x00000001

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", POINT),
                ("mouseData", ctypes.c_ulong),
                ("flags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
HHOOK = ctypes.c_void_p
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(MSLLHOOKSTRUCT))

user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, ctypes.c_void_p, ctypes.c_ulong)
user32.SetWindowsHookExW.restype = HHOOK
user32.CallNextHookEx.argtypes = (HHOOK, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(MSLLHOOKSTRUCT))
user32.CallNextHookEx.restype = LRESULT
user32.PeekMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int)
user32.UnhookWindowsHookEx.argtypes = (HHOOK,)

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(ctypes.c_ulong))
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
user32.AttachThreadInput.argtypes = (ctypes.c_ulong, ctypes.c_ulong, wintypes.BOOL)
user32.AttachThreadInput.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = ctypes.c_ulong

# --- 3. 전역 변수 ---
HORIZONTAL_THRESHOLD = 15
VERTICAL_THRESHOLD = 15
# ★ 최적화 설정: 최소 이만큼 움직여야 좌표를 저장함 (픽셀 단위)
MIN_MOVE_DISTANCE = 5  
OVERLAY_TITLE = "GestureOverlay_IgnoreMe"

hook_id = None
gesture_start_pos = None
gesture_points = []
visualizer = None

# --- 4. 스마트 창 찾기 및 제스처 기능 ---

def get_target_window(pos):
    try:
        windows_at_mouse = gw.getWindowsAt(pos[0], pos[1])
        for win in windows_at_mouse:
            if win.title == OVERLAY_TITLE or win.title == "tk": 
                continue
            return win
        return gw.getActiveWindow()
    except:
        return gw.getActiveWindow()

def force_activate(win):
    if not win: return
    
    hwnd = win._hWnd
    for i in range(5):
        try:
            if user32.GetForegroundWindow() == hwnd:
                break

            foreground_hwnd = user32.GetForegroundWindow()
            foreground_thread_id = user32.GetWindowThreadProcessId(foreground_hwnd, None)
            my_thread_id = kernel32.GetCurrentThreadId()
            
            is_minimized = user32.IsIconic(hwnd)
            show_cmd = 9 if is_minimized else 5

            if foreground_thread_id != my_thread_id:
                user32.AttachThreadInput(foreground_thread_id, my_thread_id, True)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.ShowWindow(hwnd, show_cmd)
                user32.AttachThreadInput(foreground_thread_id, my_thread_id, False)
            else:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.ShowWindow(hwnd, show_cmd)
            
            time.sleep(0.02)
        except Exception as e:
            print(f"Force activate failed: {e}")
            time.sleep(0.02)

def execute_minimize(pos):
    try:
        win = get_target_window(pos)
        if win: 
            win.minimize()
            print(f"Action: 최소화 ({win.title})")
    except: pass

def execute_maximize_restore(pos):
    try:
        win = get_target_window(pos)
        if win:
            was_maximized = win.isMaximized
            force_activate(win)
            time.sleep(0.05)
            if was_maximized: 
                win.restore()
                print(f"Action: 복구 (이전 상태: 최대화) - {win.title}")
            else: 
                win.maximize()
                print(f"Action: 최대화 (이전 상태: 일반) - {win.title}")
    except: pass

def execute_close(pos):
    try:
        win = get_target_window(pos)
        if win:
            force_activate(win)
            win.close()
            print(f"Action: 창 닫기 ({win.title})")
    except: 
        pyautogui.hotkey('alt', 'f4')

def ensure_active_and_execute(pos, func):
    try:
        win = get_target_window(pos)
        if win:
            force_activate(win)
    except: pass
    func()

def execute_next_page():
    pyautogui.hotkey('alt', 'right')
    print("Action: 다음 페이지")

def execute_prev_page():
    pyautogui.hotkey('alt', 'left')
    print("Action: 이전 페이지")

def execute_copy():
    pyautogui.hotkey('ctrl', 'c')
    print("Action: 복사")

def execute_paste():
    pyautogui.hotkey('ctrl', 'v')
    print("Action: 붙여넣기")

def process_gesture_action(start_pos, end_pos):
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    
    abs_dx = abs(dx)
    abs_dy = abs(dy)

    is_gesture = False
    
    if dx < -HORIZONTAL_THRESHOLD and dy > VERTICAL_THRESHOLD:
        execute_minimize(start_pos)
        is_gesture = True
    elif dx > HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD:
        execute_maximize_restore(start_pos)
        is_gesture = True
    elif dx < -HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD:
        execute_close(start_pos)
        is_gesture = True
    elif abs_dx > HORIZONTAL_THRESHOLD and abs_dy < VERTICAL_THRESHOLD:
        if dx > 0: ensure_active_and_execute(start_pos, execute_next_page)
        else: ensure_active_and_execute(start_pos, execute_prev_page)
        is_gesture = True
    elif abs_dy > VERTICAL_THRESHOLD and abs_dx < HORIZONTAL_THRESHOLD:
        if dy < 0: ensure_active_and_execute(start_pos, execute_copy)
        else: ensure_active_and_execute(start_pos, execute_paste)
        is_gesture = True
    
    if not is_gesture:
        pyautogui.click(button='right')

# --- 6. 시각화 클래스 ---
class GestureVisualizer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(OVERLAY_TITLE)
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes('-alpha', 0.5)
        self.root.attributes('-topmost', True)
        self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
        self.root.wm_attributes('-transparentcolor', 'black')
        
        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

    def start_drawing(self):
        self.canvas.delete("all")
        self.root.deiconify()

    def update_line(self, points):
        self.canvas.delete("all")
        if len(points) > 1:
            flat_points = [coord for point in points for coord in point]
            self.canvas.create_line(flat_points, fill='magenta', width=3, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)

    def stop_drawing(self):
        self.canvas.delete("all")
        self.canvas.update_idletasks()
        self.root.withdraw()

    def loop(self):
        self.root.mainloop()

    def safe_update(self, points):
        self.root.after(0, lambda: self.update_line(points))

    def safe_show(self):
        self.root.after(0, self.start_drawing)

    def safe_hide(self):
        self.root.after(0, self.stop_drawing)

# --- 7. 훅 프로시저 ---
def hook_proc_func(nCode, wParam, lParam):
    global gesture_start_pos, gesture_points
    
    if nCode >= 0:
        struct = lParam.contents
        
        if struct.flags & LLMHF_INJECTED:
            return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

        x, y = struct.pt.x, struct.pt.y

        if wParam == WM_RBUTTONDOWN:
            gesture_start_pos = (x, y)
            gesture_points = [(x, y)]
            if visualizer: visualizer.safe_show()
            return 1

        elif wParam == WM_MOUSEMOVE:
            if gesture_start_pos is not None:
                # ★ 최적화 적용: 마지막 좌표와 현재 좌표의 거리를 계산
                # 너무 조금 움직였으면(5픽셀 미만) 저장하지 않음 -> 그리기 부하 대폭 감소
                if gesture_points:
                    last_x, last_y = gesture_points[-1]
                    dist = math.sqrt((x - last_x)**2 + (y - last_y)**2)
                    
                    if dist < MIN_MOVE_DISTANCE:
                        # 저장 안 하고 패스
                        return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

                gesture_points.append((x, y))
                if visualizer: 
                    visualizer.safe_update(gesture_points[:])

        elif wParam == WM_RBUTTONUP:
            if gesture_start_pos is not None:
                if visualizer: visualizer.safe_hide()
                
                start_pos = gesture_start_pos
                end_pos = (x, y)
                
                t = threading.Thread(target=process_gesture_action, args=(start_pos, end_pos))
                t.start()

                gesture_start_pos = None
                gesture_points = []
                return 1

    return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

pointer = HOOKPROC(hook_proc_func)

# --- 8. 메인 실행 ---
def hook_thread_func():
    global hook_id
    hook_id = user32.SetWindowsHookExW(WH_MOUSE_LL, pointer, None, 0)
    
    if not hook_id:
        print(f"❌ 훅 설치 실패! (Error Code: {ctypes.GetLastError()})")
        return

    print("✅ 훅 설치 완료: 마우스 감지 시작...")

    msg = wintypes.MSG()
    while True:
        if user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
        else:
            time.sleep(0.01)

def main():
    global visualizer
    
    visualizer = GestureVisualizer()
    t = threading.Thread(target=hook_thread_func, daemon=True)
    t.start()

    try:
        visualizer.loop()
    except KeyboardInterrupt:
        pass
    finally:
        if hook_id:
            user32.UnhookWindowsHookEx(hook_id)

if __name__ == "__main__":
    main()