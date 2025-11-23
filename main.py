import sys
import os
import ctypes
import time
import threading
import pyautogui
import pygetwindow as gw
import tkinter as tk
from ctypes import wintypes, byref

# ★ 추가: 트레이 아이콘용 라이브러리
import pystray
from PIL import Image, ImageDraw

# --- 0. 관리자 권한 강제 실행 ---
def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, ' '.join([f'"{arg}"' for arg in sys.argv]), None, 1)
    sys.exit()

# ★ [추가] EXE 안에 포함된 파일 경로를 찾아주는 함수
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller가 생성하는 임시 폴더(_MEIPASS) 경로 확인
        base_path = sys._MEIPASS
    except Exception:
        # 평소 개발 중일 때는 현재 폴더 경로
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
    
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

# --- 3. 전역 변수 및 상수 ---
HORIZONTAL_THRESHOLD = 15
VERTICAL_THRESHOLD = 15
MIN_MOVE_DIST_SQ = 25
MAX_GESTURE_POINTS = 100 
OVERLAY_TITLE = "GestureOverlay_IgnoreMe"

current_app_instance = None 

# --- 4. 로직 함수들 ---

class GestureLogic:
    def analyze(self, start_pos, end_pos):
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        abs_dx, abs_dy = abs(dx), abs(dy)
        
        if (abs_dx > 3*abs_dy) or (abs_dx > HORIZONTAL_THRESHOLD and abs_dy < VERTICAL_THRESHOLD):
            return "NEXT" if dx > 0 else "PREV"
        elif (abs_dy > 3*abs_dx) or (abs_dy > VERTICAL_THRESHOLD and abs_dx < HORIZONTAL_THRESHOLD):
            return "PASTE" if dy > 0 else "COPY"
        elif dx < -HORIZONTAL_THRESHOLD and dy > VERTICAL_THRESHOLD: return "MINIMIZE"
        elif dx > HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD: return "MAXIMIZE"
        elif dx > HORIZONTAL_THRESHOLD and dy > VERTICAL_THRESHOLD: return "CLOSE_TAB"
        elif dx < -HORIZONTAL_THRESHOLD and dy < -VERTICAL_THRESHOLD: return "CLOSE_WINDOW"
        return None

class SystemController:
    def get_target_window(self, pos):
        try:
            windows_at_mouse = gw.getWindowsAt(pos[0], pos[1])
            for win in windows_at_mouse:
                if win.title == OVERLAY_TITLE or win.title == "tk": continue
                return win
            return gw.getActiveWindow()
        except: return gw.getActiveWindow()

    def force_activate(self, win):
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

    def execute(self, action, pos):
        if not action:
            pyautogui.click(button='right')
            return
        
        # print(f"Action: {action}") # 콘솔이 없으므로 print는 생략 가능
        
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

# --- 6. 시각화 클래스 (잔상 제거 + 1픽셀 틈새 + Always On) ---
class GestureVisualizer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(OVERLAY_TITLE)
        
        self.root.overrideredirect(True)
        self.root.attributes('-alpha', 0.5)
        self.root.attributes('-topmost', True)
        
        # [작업표시줄 해결] 높이를 1픽셀 줄임 (-1)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_w}x{screen_h - 1}+0+0")
        
        self.root.wm_attributes('-transparentcolor', 'black')
        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.line_id = self.canvas.create_line(0, 0, 0, 0, fill='magenta', width=3, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True, state='hidden')
        self.root.deiconify()

    def update_line(self, points):
        if len(points) > 1:
            flat_points = [coord for point in points for coord in point]
            self.canvas.coords(self.line_id, *flat_points)

    def safe_show(self, x, y):
        def _show():
            self.canvas.coords(self.line_id, x, y, x, y)
            self.canvas.itemconfigure(self.line_id, state='normal')
        self.root.after(0, _show)

    def safe_hide(self):
        def _hide():
            self.canvas.itemconfigure(self.line_id, state='hidden')
            self.canvas.coords(self.line_id, 0, 0, 0, 0)
        self.root.after(0, _hide)

    def safe_update(self, points):
        self.root.after(0, lambda: self.update_line(points))

    def start_loop(self):
        self.root.mainloop()
    
    def quit(self):
        self.root.quit()

# --- 7. 훅 프로시저 ---
def global_hook_proc(nCode, wParam, lParam):
    if current_app_instance:
        return current_app_instance.hook_callback(nCode, wParam, lParam)
    return user32.CallNextHookEx(None, nCode, wParam, lParam)

# ★ [수정] 에러 확인용 트레이 아이콘 함수
def create_tray_icon():
    try:
        # 1. 경로 확인
        image_path = resource_path("icon.png")
        
        # 2. 이미지 로드
        return Image.open(image_path)
    except Exception as e:
        # ★ 에러가 나면 원인을 팝업창으로 띄워줍니다.
        error_msg = f"아이콘 로드 실패!\n\n오류 내용: {e}\n\n시도한 경로: {resource_path('icon.png')}"
        ctypes.windll.user32.MessageBoxW(0, error_msg, "오류 발생", 0x10)
        
        # 실패 시 기본 동그라미 그리기
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((10, 10, 54, 54), fill='magenta', outline='white')
        return image

class MouseGestureApp:
    def __init__(self):
        self.logic = GestureLogic()
        self.sys = SystemController()
        self.visualizer = GestureVisualizer()
        
        self.hook_id = None
        self.gesture_start_pos = None
        self.gesture_points = []
        self.tray_icon = None # 트레이 아이콘 객체
        
        global current_app_instance
        current_app_instance = self

    def process_action_thread(self, start_pos, end_pos):
        action = self.logic.analyze(start_pos, end_pos)
        self.sys.execute(action, start_pos)

    def hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0:
            struct = lParam.contents
            if struct.flags & LLMHF_INJECTED: return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

            x, y = struct.pt.x, struct.pt.y

            if wParam == WM_RBUTTONDOWN:
                self.gesture_start_pos = (x, y)
                self.gesture_points = [(x, y)]
                self.visualizer.safe_show(x, y)
                return 1

            elif wParam == WM_MOUSEMOVE:
                if self.gesture_start_pos is not None:
                    if len(self.gesture_points) > MAX_GESTURE_POINTS:
                        self.gesture_start_pos = None
                        self.gesture_points = []
                        self.visualizer.safe_hide()
                        return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

                    if self.gesture_points:
                        last_x, last_y = self.gesture_points[-1]
                        dist_sq = (x - last_x)**2 + (y - last_y)**2
                        if dist_sq < MIN_MOVE_DIST_SQ:
                            return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

                    self.gesture_points.append((x, y))
                    self.visualizer.safe_update(self.gesture_points[:])

            elif wParam == WM_RBUTTONUP:
                if self.gesture_start_pos is not None:
                    self.visualizer.safe_hide()
                    start_pos = self.gesture_start_pos
                    end_pos = (x, y)
                    t = threading.Thread(target=self.process_action_thread, args=(start_pos, end_pos))
                    t.start()
                    self.gesture_start_pos = None
                    self.gesture_points = []
                    return 1

        return user32.CallNextHookEx(self.hook_id, nCode, wParam, lParam)

    def _hook_thread_proc(self):
        pointer = HOOKPROC(global_hook_proc)
        self.hook_id = user32.SetWindowsHookExW(WH_MOUSE_LL, pointer, None, 0)
        if not self.hook_id: return

        msg = wintypes.MSG()
        while self.hook_id: # 훅 ID가 있을 때만 루프
            if user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
            else: time.sleep(0.01)

    # ★ 트레이 아이콘 스레드 함수
    def _tray_thread_proc(self):
        def on_quit(icon, item):
            icon.stop() # 트레이 아이콘 종료
            self.stop() # 앱 전체 종료 호출

        self.tray_icon = pystray.Icon("MouseGesture", create_tray_icon(), "마우스 제스처 (Mouse Gesture)")
        self.tray_icon.menu = pystray.Menu(
            pystray.MenuItem('종료 (Exit)', on_quit)
        )
        self.tray_icon.run()

    # 앱 종료 처리
    def stop(self):
        # 1. 훅 해제
        if self.hook_id:
            user32.UnhookWindowsHookEx(self.hook_id)
            self.hook_id = None
        # 2. GUI 종료
        self.visualizer.quit()
        # 3. 강제 프로세스 종료 (스레드 정리 보장)
        os._exit(0)

    def run(self):
        # 1. 훅 스레드 시작
        t_hook = threading.Thread(target=self._hook_thread_proc, daemon=True)
        t_hook.start()
        
        # 2. 트레이 아이콘 스레드 시작 (★ 추가됨)
        t_tray = threading.Thread(target=self._tray_thread_proc, daemon=True)
        t_tray.start()
        
        # 3. 메인 스레드는 GUI 루프
        try: self.visualizer.start_loop()
        except: pass
        finally:
            self.stop()

if __name__ == "__main__":
    app = MouseGestureApp()
    app.run()
    
