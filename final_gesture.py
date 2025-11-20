import sys
import ctypes
import time
import threading
import pyautogui
import pygetwindow as gw
import tkinter as tk
from ctypes import wintypes, byref

# --- 1. 설정 및 최적화 ---
# Pyautogui의 기본 딜레이를 제거하여 반응 속도를 높임
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
HORIZONTAL_THRESHOLD = 20
VERTICAL_THRESHOLD = 20

hook_id = None
gesture_start_pos = None
gesture_points = []
visualizer = None

# --- 4. 제스처 기능 함수들 ---
def execute_minimize():
    try:
        win = gw.getActiveWindow()
        if win: win.minimize()
        print("Action: 최소화")
    except: pass

def execute_maximize_restore():
    try:
        win = gw.getActiveWindow()
        if win:
            if win.isMaximized: win.restore()
            else: win.maximize()
        print("Action: 최대화/복구")
    except: pass

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

def execute_close():
    pyautogui.hotkey('alt', 'f4')
    print("Action: 창 닫기")

# --- 5. 비동기 처리 로직 (버벅임 해결의 핵심) ---

def process_gesture_action(start_pos, end_pos):
    """
    제스처 분석 및 실행을 담당하는 함수.
    훅킹 스레드가 아닌 별도의 스레드에서 실행됨.
    """
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    
    abs_dx = abs(dx)
    abs_dy = abs(dy)

    is_gesture = False

    # HORIZONTAL_THRESHOLD, VERTICAL_THRESHOLD 미세 조정용 print
    print(f"(dx, dy) = {dx, dy}")

    # 제스처 판별 로직
    if dx < -HORIZONTAL_THRESHOLD and dy > VERTICAL_THRESHOLD:
        execute_minimize()
        is_gesture = True
    elif dx > HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD:
        execute_maximize_restore()
        is_gesture = True
    elif dx < -HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD:
        execute_close()
        is_gesture = True
    elif abs_dx > HORIZONTAL_THRESHOLD and abs_dy < VERTICAL_THRESHOLD:
        if dx > 0: execute_next_page()
        else: execute_prev_page()
        is_gesture = True
    elif abs_dy > VERTICAL_THRESHOLD and abs_dx < HORIZONTAL_THRESHOLD:
        if dy < 0: execute_copy()
        else: execute_paste()
        is_gesture = True
    
    # 제스처가 아니면 일반 우클릭 발생
    if not is_gesture:
        # 좌표 인자 없이 호출하면 '현재 위치'에서 클릭하므로 마우스 이동(버벅임)이 발생하지 않음
        pyautogui.click(button='right')

# --- 6. 시각화 클래스 (잔상 제거 버전) ---
class GestureVisualizer:
    def __init__(self):
        self.root = tk.Tk()
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
        
        # 기계적 입력(INJECTED)은 무조건 패스 (무한루프 방지)
        if struct.flags & LLMHF_INJECTED:
            return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

        x, y = struct.pt.x, struct.pt.y

        if wParam == WM_RBUTTONDOWN:
            gesture_start_pos = (x, y)
            gesture_points = [(x, y)]
            if visualizer: visualizer.safe_show()
            return 1  # 즉시 차단

        elif wParam == WM_MOUSEMOVE:
            if gesture_start_pos is not None:
                gesture_points.append((x, y))
                if visualizer: 
                    visualizer.safe_update(gesture_points[:])
            # 이동은 차단하지 않음 (시스템 성능 영향 최소화)

        elif wParam == WM_RBUTTONUP:
            if gesture_start_pos is not None:
                # 1. 시각화 끄기 (Non-blocking)
                if visualizer: visualizer.safe_hide()
                
                start_pos = gesture_start_pos # 값 복사
                end_pos = (x, y)
                
                # 2. ★ 핵심 변경: 별도 스레드에서 로직 처리 ★
                # 훅 프로시저 안에서 pyautogui를 실행하면 마우스가 멈칫함.
                # 따라서 스레드를 띄워 "나중에 실행해"라고 던져두고 훅은 바로 리턴해야 함.
                t = threading.Thread(target=process_gesture_action, args=(start_pos, end_pos))
                t.start()

                # 초기화
                gesture_start_pos = None
                gesture_points = []
                
                return 1  # 윈도우에게 "이미 처리됨" 신호 보냄

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
        # PeekMessage로 CPU 점유율 낮추면서 메시지 처리
        if user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))
        else:
            time.sleep(0.01)

def main():
    global visualizer
    print("=== 부드러운 마우스 제스처 (No Lag) ===")
    
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