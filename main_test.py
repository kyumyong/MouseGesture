import sys
import ctypes
from ctypes import wintypes, c_void_p, c_int

# --- 1. 타입 및 상수 정의 (64비트 호환성 확보) ---
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_MOUSE_LL = 14
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

# C 타입 정의 (64비트에서 핸들은 8바이트)
LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
HHOOK = ctypes.c_void_p
HINSTANCE = ctypes.c_void_p

# 콜백 함수 타입 정의
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, c_int, wintypes.WPARAM, wintypes.LPARAM)

# ★ 중요: 윈도우 API 함수의 인자 타입(Argtypes) 강제 설정 ★
# 이렇게 해야 파이썬이 64비트 주소를 잘라먹지 않고 제대로 전달합니다.
user32.SetWindowsHookExW.argtypes = (c_int, HOOKPROC, HINSTANCE, ctypes.c_ulong)
user32.SetWindowsHookExW.restype = HHOOK

user32.CallNextHookEx.argtypes = (HHOOK, c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT

user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, c_int, c_int)
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = HINSTANCE

# --- 2. 훅 프로시저 (이벤트 처리) ---
def hook_proc(nCode, wParam, lParam):
    if nCode >= 0:
        if wParam in (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_CONTEXTMENU):
            # 우클릭 차단 로그 (너무 많이 뜨면 주석 처리하세요)
            print(f"🚫 우클릭 차단됨 (Event: {hex(wParam)})")
            return 1  # 이벤트 제거 (Block)
    return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

# 콜백 함수 포인터 생성 (가비지 컬렉션 방지를 위해 전역 변수로 유지)
pointer = HOOKPROC(hook_proc)
hook_id = None

# --- 3. 메인 실행 로직 ---
def main():
    global hook_id
    
    # 1. 현재 실행 중인 모듈(.exe)의 핸들 가져오기
    # 파이썬 3.11에서는 None을 넣으면 python.exe 핸들을 잘 가져옵니다.
    h_mod = kernel32.GetModuleHandleW(None)
    
    print(f"🔍 핸들 정보 확인: {h_mod}")
    if not h_mod:
        print("❌ 모듈 핸들을 가져오지 못했습니다.")
        return

    print("🚀 우클릭 차단 시작 (종료하려면 Ctrl+C)...")
    
    # 2. 훅 설치
    # h_mod: 현재 프로세스 핸들, 0: 모든 스레드 감시
    hook_id = user32.SetWindowsHookExW(WH_MOUSE_LL, pointer, h_mod, 0)

    if not hook_id:
        err = ctypes.GetLastError()
        print(f"\n❌ 훅 설치 실패! (Error Code: {err})")
        
        if err == 126:
            print("   👉 여전히 126 에러라면, '재부팅'을 꼭 하셔야 합니다.")
            print("   👉 Fasoo 삭제 후 레지스트리 변경 사항은 재부팅 후에 적용됩니다.")
        return

    # 3. 메시지 루프 (윈도우 이벤트 대기)
    try:
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        print("\n🛑 종료 요청 감지.")
    finally:
        if hook_id:
            user32.UnhookWindowsHookEx(hook_id)
            print("✅ 훅 해제 완료.")

if __name__ == "__main__":
    main()