import sys
import ctypes
import time
import threading
import pyautogui
import pygetwindow as gw
import tkinter as tk
# math 모듈 제거 (제곱근 안 씀)
from ctypes import wintypes, byref

# --- 0. 관리자 권한 ---
def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, ' '.join([f'"{arg}"' for arg in sys.argv]), None, 1)
    sys.exit()

# --- 1. 설정 ---
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False

# --- 2. WinAPI ---
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
    _fields_ = [("pt", POINT), ("mouseData", ctypes.c_ulong), ("flags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

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

# --- 3. 전역 변수 및 최적화 상수 ---
HORIZONTAL_THRESHOLD = 15
VERTICAL_THRESHOLD = 15

# ★ 최적화 1: 제곱근 계산을 피하기 위해 '거리의 제곱'을 기준값으로 사용
# 5픽셀 * 5픽셀 = 25
MIN_MOVE_DIST_SQ = 25 

OVERLAY_TITLE = "GestureOverlay_IgnoreMe"

hook_id = None
gesture_start_pos = None
gesture_points = []
visualizer = None

# --- 4. 로직 함수들 ---

def get_target_window(pos):
    try:
        windows_at_mouse = gw.getWindowsAt(pos[0], pos[1])
        for win in windows_at_mouse:
            if win.title == OVERLAY_TITLE or win.title == "tk": continue
            return win
        return gw.getActiveWindow()
    except: return gw.getActiveWindow()

def force_activate(win):
    if not win: return
    hwnd = win._hWnd
    for i in range(5):
        try:
            if user32.GetForegroundWindow() == hwnd: break
            
            fg_hwnd = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            my_tid = kernel32.GetCurrentThreadId()
            show_cmd = 9 if user32.IsIconic(hwnd) else 5

            if fg_tid != my_tid:
                user32.AttachThreadInput(fg_tid, my_tid, True)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.ShowWindow(hwnd, show_cmd)
                user32.AttachThreadInput(fg_tid, my_tid, False)
            else:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.ShowWindow(hwnd, show_cmd)
            time.sleep(0.02)
        except: time.sleep(0.02)

def execute_minimize(pos):
    try:
        win = get_target_window(pos)
        if win: win.minimize(); print(f"Action: 최소화 ({win.title})")
    except: pass

def execute_maximize_restore(pos):
    try:
        win = get_target_window(pos)
        if win:
            was_max = win.isMaximized
            force_activate(win)
            time.sleep(0.05)
            if was_max: win.restore(); print(f"Action: 복구 - {win.title}")
            else: win.maximize(); print(f"Action: 최대화 - {win.title}")
    except: pass

def execute_close(pos):
    try:
        win = get_target_window(pos)
        if win:
            force_activate(win)
            win.close()
            print(f"Action: 닫기 ({win.title})")
    except: pyautogui.hotkey('alt', 'f4')

def ensure_active_and_execute(pos, func):
    try:
        win = get_target_window(pos)
        if win: force_activate(win)
    except: pass
    func()

# 기능 맵핑
def execute_next_page(): pyautogui.hotkey('alt', 'right'); print("Action: Next")
def execute_prev_page(): pyautogui.hotkey('alt', 'left'); print("Action: Prev")
def execute_copy(): pyautogui.hotkey('ctrl', 'c'); print("Action: Copy")
def execute_paste(): pyautogui.hotkey('ctrl', 'v'); print("Action: Paste")

def process_gesture_action(start_pos, end_pos):
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    abs_dx, abs_dy = abs(dx), abs(dy)
    is_gesture = False
    
    if dx < -HORIZONTAL_THRESHOLD and dy > VERTICAL_THRESHOLD: execute_minimize(start_pos); is_gesture = True
    elif dx > HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD: execute_maximize_restore(start_pos); is_gesture = True
    elif dx < -HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD: execute_close(start_pos); is_gesture = True
    elif abs_dx > HORIZONTAL_THRESHOLD and abs_dy < VERTICAL_THRESHOLD:
        ensure_active_and_execute(start_pos, execute_next_page if dx > 0 else execute_prev_page)
        is_gesture = True
    elif abs_dy > VERTICAL_THRESHOLD and abs_dx < HORIZONTAL_THRESHOLD:
        ensure_active_and_execute(start_pos, execute_copy if dy < 0 else execute_paste)
        is_gesture = True
    
    if not is_gesture: pyautogui.click(button='right')

# --- 6. 시각화 클래스 (객체 재사용 최적화 적용) ---
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
        
        # ★ 최적화 2: 선 객체를 미리 하나 만들어둠 (처음엔 숨김 상태)
        self.line_id = self.canvas.create_line(0, 0, 0, 0, fill='magenta', width=3, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True, state='hidden')

    def start_drawing(self):
        # 시작할 때 선 좌표 초기화하고 숨김 해제
        self.canvas.coords(self.line_id, 0, 0, 0, 0)
        self.canvas.itemconfigure(self.line_id, state='normal') # 보이기
        self.root.deiconify()

    def update_line(self, points):
        if len(points) > 1:
            flat_points = [coord for point in points for coord in point]
            # ★ 최적화 2 핵심: delete/create 대신 coords만 수정
            # 기존 객체의 좌표만 바꾸는 것이 훨씬 빠름
            self.canvas.coords(self.line_id, *flat_points)

    def stop_drawing(self):
        # 다 쓰면 선을 숨기고 창도 숨김
        self.canvas.itemconfigure(self.line_id, state='hidden')
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
        if struct.flags & LLMHF_INJECTED: return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

        x, y = struct.pt.x, struct.pt.y

        if wParam == WM_RBUTTONDOWN:
            gesture_start_pos = (x, y)
            gesture_points = [(x, y)]
            if visualizer: visualizer.safe_show()
            return 1

        elif wParam == WM_MOUSEMOVE:
            if gesture_start_pos is not None:
                if gesture_points:
                    last_x, last_y = gesture_points[-1]
                    # ★ 최적화 1: 제곱근 없이 거리 제곱 비교 (sqrt 제거)
                    dist_sq = (x - last_x)**2 + (y - last_y)**2
                    if dist_sq < MIN_MOVE_DIST_SQ: # 25 (5^2) 보다 작으면 무시
                        return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

                gesture_points.append((x, y))
                if visualizer: visualizer.safe_update(gesture_points[:])

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

def hook_thread_func():
    global hook_id
    hook_id = user32.SetWindowsHookExW(WH_MOUSE_LL, pointer, None, 0)
    if not hook_id: return
    msg = wintypes.MSG()
    while True:
        if user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
        else: time.sleep(0.01)

def main():
    global visualizer
    visualizer = GestureVisualizer()
    t = threading.Thread(target=hook_thread_func, daemon=True)
    t.start()
    try: visualizer.loop()
    except: pass
    finally:
        if hook_id: user32.UnhookWindowsHookEx(hook_id)

if __name__ == "__main__":
    main()