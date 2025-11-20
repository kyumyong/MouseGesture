import sys
import ctypes
import time
import threading
import pyautogui
import pygetwindow as gw
import tkinter as tk
from ctypes import wintypes, byref

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

# --- 3. 전역 변수 ---
HORIZONTAL_THRESHOLD = 50
VERTICAL_THRESHOLD = 50
OVERLAY_TITLE = "GestureOverlay_IgnoreMe"  # 우리 프로그램의 창 제목

hook_id = None
gesture_start_pos = None
gesture_points = []
visualizer = None

# --- 4. 스마트 창 찾기 및 제스처 기능 ---

def get_target_window(pos):
    """
    마우스 위치에 있는 창들 중, '제스처 시각화 창(Overlay)'을 제외한
    가장 위에 있는 실제 앱 창을 찾습니다.
    """
    try:
        # 1. 현재 마우스 좌표에 있는 모든 창을 리스트로 가져옴
        windows_at_mouse = gw.getWindowsAt(pos[0], pos[1])
        
        for win in windows_at_mouse:
            # ★ 핵심 수정: 우리 자신의 시각화 창이나 빈 제목은 무시하고 건너뜀
            if win.title == OVERLAY_TITLE or win.title == "tk": 
                continue
            
            # 정상적인 창을 찾으면 즉시 반환
            return win
            
        # 2. 마우스 위치에서 적절한 창을 못 찾으면 활성 창 반환
        return gw.getActiveWindow()
    except:
        return gw.getActiveWindow()

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
            if win.isMaximized: win.restore()
            else: win.maximize()
            print(f"Action: 최대화/복구 ({win.title})")
    except: pass

def execute_close(pos):
    try:
        win = get_target_window(pos)
        if win:
            win.close()
            print(f"Action: 창 닫기 ({win.title})")
    except: 
        pyautogui.hotkey('alt', 'f4')

def ensure_active_and_execute(pos, func):
    try:
        win = get_target_window(pos)
        if win:
            try:
                win.activate()
            except: pass
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


# --- 5. 비동기 처리 로직 ---

def process_gesture_action(start_pos, end_pos):
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    
    abs_dx = abs(dx)
    abs_dy = abs(dy)

    is_gesture = False
    
    if dx < -HORIZONTAL_THRESHOLD and dy > VERTICAL_THRESHOLD:
        execute_minimize(start_pos) # ↘
        is_gesture = True
    elif dx > HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD:
        execute_maximize_restore(start_pos) # ↗
        is_gesture = True
    elif dx < -HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD:
        execute_close(start_pos) # ↖
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
        # ★ 핵심 수정: 창 제목을 설정하여 필터링할 수 있게 함
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
            self.canvas.create_line(flat_points, fill='green', width=3, capstyle=tk.ROUND, smooth=True)

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
    print("=== 스마트 마우스 제스처 (자기 자신 무시 기능 추가) ===")
    
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