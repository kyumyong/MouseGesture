import sys
import ctypes
import time  # time 모듈 추가
from ctypes import wintypes, c_void_p, c_int, byref

# --- 1. 타입 및 상수 정의 ---
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_MOUSE_LL = 14
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_QUIT = 0x0012
PM_REMOVE = 0x0001  # 메시지를 큐에서 제거하는 옵션

# 64비트 호환 타입 정의
LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
HHOOK = ctypes.c_void_p
HINSTANCE = ctypes.c_void_p
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, c_int, wintypes.WPARAM, wintypes.LPARAM)

# API 함수 인자 타입 설정
user32.SetWindowsHookExW.argtypes = (c_int, HOOKPROC, HINSTANCE, ctypes.c_ulong)
user32.SetWindowsHookExW.restype = HHOOK

user32.CallNextHookEx.argtypes = (HHOOK, c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT

# GetMessage 대신 사용할 PeekMessage 정의
user32.PeekMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, c_int, c_int, c_int)
user32.PeekMessageW.restype = wintypes.BOOL

user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)

kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = HINSTANCE

# 전역 변수
hook_id = None

# --- 2. 훅 프로시저 ---
def hook_proc(nCode, wParam, lParam):
    if nCode >= 0:
        if wParam in (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_CONTEXTMENU):
            return 1  # 우클릭 차단
    return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

pointer = HOOKPROC(hook_proc)

# --- 3. 메인 실행 로직 ---
def main():
    global hook_id
    
    h_mod = kernel32.GetModuleHandleW(None)
    
    print("🚀 우클릭 차단 시작 (종료하려면 Ctrl+C를 누르세요)...")
    
    # 훅 설치
    hook_id = user32.SetWindowsHookExW(WH_MOUSE_LL, pointer, h_mod, 0)

    if not hook_id:
        print(f"❌ 훅 설치 실패! (Error: {ctypes.GetLastError()})")
        return

    msg = wintypes.MSG()
    
    # 🌟 핵심 변경 사항: Non-blocking 루프 🌟
    try:
        while True:
            # 1. 메시지가 있는지 확인 (Peek)하고 있으면 가져옴 (PM_REMOVE)
            # 메시지가 없으면 즉시 False 반환 (기다리지 않음)
            if user32.PeekMessageW(byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    break
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
            else:
                # 2. 메시지가 없으면 0.01초 쉽니다.
                # 이 'sleep' 시간 동안 파이썬은 Ctrl+C(KeyboardInterrupt)를 감지할 수 있습니다.
                time.sleep(0.01)
                
    except KeyboardInterrupt:
        print("\n🛑 [Ctrl+C 감지] 프로그램을 종료합니다...")
    finally:
        if hook_id:
            user32.UnhookWindowsHookEx(hook_id)
            print("✅ 훅 해제 완료.")

if __name__ == "__main__":
    main()