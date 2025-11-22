import sys
import ctypes
import time
import threading
import pyautogui
import pygetwindow as gw
import tkinter as tk
from ctypes import wintypes, byref

# --- 0. 관리자 권한 강제 실행 ---
def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

if not is_admin():
    # 현재 스크립트를 관리자 권한('runas')으로 재실행
    # 파이썬 인터프리터(sys.executable)로 현재 파일(__file__)을 실행
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, ' '.join([f'"{arg}"' for arg in sys.argv]), None, 1)
    sys.exit()

# --- 1. 설정 ---
pyautogui.PAUSE = 0
# Pyautogui 안전장치 해제 (드래그 중 모서리로 가면 멈추는 기능 끄기)
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

# AttachThreadInput 및 창 제어 API
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
# ★ 추가: 화면 맨 위로 올리는 강력한 API
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = ctypes.c_ulong

# --- 3. 전역 변수 및 최적화 상수 ---
HORIZONTAL_THRESHOLD = 15
VERTICAL_THRESHOLD = 15

# ★ 최적화 1: 제곱근 계산을 피하기 위해 '거리의 제곱'을 기준값으로 사용
# 5픽셀 * 5픽셀 = 25
MIN_MOVE_DIST_SQ = 25  # 5픽셀 이동 제한

# ★ 추가된 최적화: 제스처 포인트 개수 제한 (너무 길면 취소)
# 100개 * 5px = 약 500px 이상 이동하면 취소됨
MAX_GESTURE_POINTS = 100 

OVERLAY_TITLE = "GestureOverlay_IgnoreMe"  # 우리 프로그램의 창 제목

# [글로벌 훅 연결을 위한 변수]
current_app_instance = None 

# --- 4. 로직 함수들 (클래스로 분리됨) ---

class GestureLogic:
    def analyze(self, start_pos, end_pos):
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        abs_dx, abs_dy = abs(dx), abs(dy)
        
        # 1. 수평 제스처 우선 확인 (비율 3배 이상 or 수직 이동 미미함)
        if (abs_dx > 3*abs_dy) or (abs_dx > HORIZONTAL_THRESHOLD and abs_dy < VERTICAL_THRESHOLD):
            return "NEXT" if dx > 0 else "PREV"
            
        # 2. 수직 제스처 확인 (비율 3배 이상 or 수평 이동 미미함)
        elif (abs_dy > 3*abs_dx) or (abs_dy > VERTICAL_THRESHOLD and abs_dx < HORIZONTAL_THRESHOLD):
            return "PASTE" if dy > 0 else "COPY"
            
        # 3. 그 외엔 대각선 제스처 확인
        elif dx < -HORIZONTAL_THRESHOLD and dy > VERTICAL_THRESHOLD: return "MINIMIZE"
        elif dx > HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD: return "MAXIMIZE"
        elif dx > HORIZONTAL_THRESHOLD and dy > VERTICAL_THRESHOLD: return "CLOSE_TAB"
        elif dx < -HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD: return "CLOSE_WINDOW"
        
        return None

class SystemController:
    def get_target_window(self, pos):
        try:
            # 1. 현재 마우스 좌표에 있는 모든 창을 리스트로 가져옴
            windows_at_mouse = gw.getWindowsAt(pos[0], pos[1])

            for win in windows_at_mouse:
                # ★ 핵심 수정: 우리 자신의 시각화 창이나 빈 제목은 무시하고 건너뜀
                if win.title == OVERLAY_TITLE or win.title == "tk": continue
                # 정상적인 창을 찾으면 즉시 반환
                return win
            # 2. 마우스 위치에서 적절한 창을 못 찾으면 활성 창 반환
            return gw.getActiveWindow()
        except: return gw.getActiveWindow()

    def force_activate(self, win):
        if not win: return
        hwnd = win._hWnd

        # 최대 5번 시도 (성공할 때까지)
        for i in range(5):
            try:
                # 이미 맨 앞이라면 중단
                if user32.GetForegroundWindow() == hwnd: break
                fg_hwnd = user32.GetForegroundWindow()
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                my_tid = kernel32.GetCurrentThreadId()
                # 최소화 상태면 SW_RESTORE(9), 아니면 SW_SHOW(5)
                show_cmd = 9 if user32.IsIconic(hwnd) else 5

                if fg_tid != my_tid:
                    # 1. 스레드 연결
                    user32.AttachThreadInput(fg_tid, my_tid, True)
                    # 2. 명령 난사 (BringWindowToTop 추가)
                    user32.BringWindowToTop(hwnd)   # Z-Order 위로
                    user32.SetForegroundWindow(hwnd) # 포커스 이동
                    user32.ShowWindow(hwnd, show_cmd) # 화면 표시
                    # 3. 연결 해제
                    user32.AttachThreadInput(fg_tid, my_tid, False)
                else:
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.ShowWindow(hwnd, show_cmd)
                # 실패했을 경우를 대비해 아주 짧게 대기 후 재시도
                time.sleep(0.02)
            except: time.sleep(0.02)

    def execute(self, action, pos):
        if not action:
            # 제스처가 아니면 일반 우클릭 발생
            # 좌표 인자 없이 호출하면 '현재 위치'에서 클릭하므로 마우스 이동(버벅임)이 발생하지 않음
            pyautogui.click(button='right')
            return

        print(f"Action: {action}")
        
        if action in ["MINIMIZE", "MAXIMIZE", "CLOSE_TAB", "CLOSE_WINDOW"]:
            win = self.get_target_window(pos)
            if win:
                if action == "MINIMIZE": win.minimize()
                elif action == "MAXIMIZE":
                    self.force_activate(win); time.sleep(0.05)
                    if win.isMaximized: win.restore()
                    else: win.maximize()
                elif action == "CLOSE_TAB":
                    self.force_activate(win); pyautogui.hotkey('ctrl', 'w')
                elif action == "CLOSE_WINDOW":
                    self.force_activate(win); pyautogui.hotkey('alt', 'f4')
        
        else:
            ensure_win = self.get_target_window(pos)
            if ensure_win: self.force_activate(ensure_win)
            
            if action == "NEXT": pyautogui.hotkey('alt', 'right')
            elif action == "PREV": pyautogui.hotkey('alt', 'left')
            elif action == "COPY": pyautogui.hotkey('ctrl', 'c')
            elif action == "PASTE": pyautogui.hotkey('ctrl', 'v')

# --- 6. 시각화 클래스 (객체 재사용 최적화 적용) ---
class GestureVisualizer:
    def __init__(self):
        self.root = tk.Tk()
        # ★ 핵심 수정: 창 제목을 설정하여 필터링할 수 있게 함
        self.root.title(OVERLAY_TITLE)
        
        self.root.overrideredirect(True)
        self.root.attributes('-alpha', 0.5)
        self.root.attributes('-topmost', True)
        
        # [작업표시줄 해결] 높이를 1픽셀 줄임 (-1)
        # 이렇게 하면 마우스가 화면 맨 아래에 닿았을 때 투명 창이 아니라 OS 바닥을 건드리게 됨
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_w}x{screen_h - 1}+0+0")
        
        self.root.wm_attributes('-transparentcolor', 'black')
        
        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        # ★ 최적화 2: 선 객체를 미리 하나 만들어둠 (처음엔 숨김 상태)
        self.line_id = self.canvas.create_line(0, 0, 0, 0, fill='magenta', width=3, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True, state='hidden')
        
        # [Best Practice 적용] 창을 항상 띄워두고(deiconify), 선만 숨김(state='hidden')
        self.root.deiconify()

    def update_line(self, points):
        if len(points) > 1:
            flat_points = [coord for point in points for coord in point]
            # ★ 최적화 2 핵심: delete/create 대신 coords만 수정
            # 기존 객체의 좌표만 바꾸는 것이 훨씬 빠름
            self.canvas.coords(self.line_id, *flat_points)

    # --- [Best Practice 적용: 창은 건드리지 않고 선만 껐다 킴] ---
    def safe_show(self, x, y):
        # 창은 이미 떠 있음. 선을 현재 위치로 옮기고 보이게 함
        def _show():
            self.canvas.coords(self.line_id, x, y, x, y)
            self.canvas.itemconfigure(self.line_id, state='normal')
        self.root.after(0, _show)

    def safe_hide(self):
        # 선만 안 보이게 숨김
        def _hide():
            self.canvas.itemconfigure(self.line_id, state='hidden')
            self.canvas.coords(self.line_id, 0, 0, 0, 0)
        self.root.after(0, _hide)

    def safe_update(self, points):
        self.root.after(0, lambda: self.update_line(points))

    def start_loop(self):
        self.root.mainloop()

# --- 7. 훅 프로시저 (전역 함수) ---
def global_hook_proc(nCode, wParam, lParam):
    if current_app_instance:
        return current_app_instance.hook_callback(nCode, wParam, lParam)
    return user32.CallNextHookEx(None, nCode, wParam, lParam)

class MouseGestureApp:
    def __init__(self):
        self.logic = GestureLogic()
        self.sys = SystemController()
        self.visualizer = GestureVisualizer()
        
        self.hook_id = None
        self.gesture_start_pos = None
        self.gesture_points = []
        
        global current_app_instance
        current_app_instance = self

    # ★ 핵심 변경: 별도 스레드에서 로직 처리 ★
    def process_action_thread(self, start_pos, end_pos):
        action = self.logic.analyze(start_pos, end_pos)
        self.sys.execute(action, start_pos)

    def hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0:
            struct = lParam.contents
            # 기계가 만든 가짜 입력(INJECTED)은 통과 (무한 루프 방지)
            if struct.flags & LLMHF_INJECTED: return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

            x, y = struct.pt.x, struct.pt.y

            if wParam == WM_RBUTTONDOWN:
                self.gesture_start_pos = (x, y)
                self.gesture_points = [(x, y)]
                # 잔상 해결: 현재 위치 (x, y)를 넘겨주어 그곳에서 그리기 시작하도록 함
                self.visualizer.safe_show(x, y)
                return 1  # 즉시 차단

            elif wParam == WM_MOUSEMOVE:
                if self.gesture_start_pos is not None:
                    # ★ CPU 방어 코드: 너무 길어지면 추적 중단하고 빠져나감
                    if len(self.gesture_points) > MAX_GESTURE_POINTS:
                        self.gesture_start_pos = None
                        self.gesture_points = []
                        self.visualizer.safe_hide()
                        # 이후 움직임은 시스템에 맡김 (차단 안 함)
                        return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

                    if self.gesture_points:
                        last_x, last_y = self.gesture_points[-1]
                        # ★ 최적화 1: 제곱근 없이 거리 제곱 비교 (sqrt 제거)
                        dist_sq = (x - last_x)**2 + (y - last_y)**2
                        if dist_sq < MIN_MOVE_DIST_SQ: # 25 (5^2) 보다 작으면 무시
                            return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

                    self.gesture_points.append((x, y))
                    self.visualizer.safe_update(self.gesture_points[:])

            elif wParam == WM_RBUTTONUP:
                # gesture_start_pos가 None이면(길이 초과로 취소된 경우) 여기 안 걸리고 아래로 통과됨
                if self.gesture_start_pos is not None:
                    # 1. 시각화 끄기 (Non-blocking)
                    self.visualizer.safe_hide()
                    start_pos = self.gesture_start_pos
                    end_pos = (x, y)
                    
                    t = threading.Thread(target=self.process_action_thread, args=(start_pos, end_pos))
                    t.start()
                    
                    # 초기화
                    self.gesture_start_pos = None
                    self.gesture_points = []
                    return 1  # 윈도우에게 "이미 처리됨" 신호 보냄

        return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

    def _hook_thread_proc(self):
        pointer = HOOKPROC(global_hook_proc)
        # 1. 윈도우 훅 설치 (감시 시작)
        self.hook_id = user32.SetWindowsHookExW(WH_MOUSE_LL, pointer, None, 0)
        if not self.hook_id: return

        # 2. 메시지 루프 (감시 유지)
        msg = wintypes.MSG()
        while True:
            # 윈도우 메시지 큐 확인 (PeekMessage)
            # PeekMessage로 CPU 점유율 낮추면서 메시지 처리
            if user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
            # 메시지가 없으면 CPU를 위해 잠시 쉼. PeekMessageW는 쉬지 않고 무한 반복하므로, CPU 사용량이 100%로 치솟을 수 있습니다
            # 이를 막기 위해 "할 일 없으면 0.01초 쉬어라"라고 명령해 CPU 점유율을 0~1%대로 낮추는 핵심 코드입니다
            else: time.sleep(0.01)

    def run(self):
        t = threading.Thread(target=self._hook_thread_proc, daemon=True)
        t.start()
        
        try: self.visualizer.start_loop()
        except: pass
        finally:
            if self.hook_id: user32.UnhookWindowsHookEx(self.hook_id)

if __name__ == "__main__":
    app = MouseGestureApp()
    app.run()