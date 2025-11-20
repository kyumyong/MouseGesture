import pyautogui
import pygetwindow as gw
from pynput import mouse
import tkinter as tk
from threading import Thread
import atexit

# --- 제스처 시각화 ---

class GestureVisualizer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # 초기 창 숨기기
        self.root.overrideredirect(True)  # 창 테두리 및 제목 표시줄 제거
        self.root.attributes('-alpha', 0.5)  # 창 투명도 설정
        self.root.attributes('-topmost', True)  # 항상 위에 표시
        self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")

        self.canvas = tk.Canvas(self.root, bg='black', highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.root.wm_attributes('-transparentcolor', 'black')

        # 새로 추가: 선이 남는 문제 방지를 위해 double-buffering 비슷한 효과 적용
        self.canvas.configure(scrollregion=(0,0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()))

    def draw_gesture(self, points):
        """캔버스에 제스처 경로를 그립니다."""
        self.canvas.delete("all")  # 이전 그림 지우기
        if len(points) > 1:
            self.canvas.create_line(points, fill='green', width=3, capstyle=tk.ROUND, smooth=True)
        # 새로 추가: 즉시 업데이트하여 잔상 방지
        self.canvas.update_idletasks()


    def show(self):
        """창을 화면에 표시합니다."""
        self.root.deiconify()
        self.canvas.delete("all")
        self.canvas.update_idletasks()

    # def hide_and_destroy(self):
    #     """창을 숨기고 파괴합니다."""
    #     self.root.withdraw()
    #     self.root.destroy()

    def hide(self):
        """창을 숨기고 캔버스를 지웁니다."""
        self.canvas.delete("all")
        self.canvas.update_idletasks()
        self.root.withdraw()

    # def run(self):
    #     """Tkinter 메인 루프를 실행합니다."""
    #     self.show()
    #     self.root.mainloop()

    def run(self):
        """Tkinter 메인 루프를 실행합니다."""
        self.root.mainloop()

    def destroy(self):
        """Tkinter 창을 파괴합니다."""
        self.root.quit()
        self.root.destroy()


# 제스처 데이터를 저장하기 위한 전역 변수
is_right_button_pressed = False
gesture_points = []
visualizer = GestureVisualizer() # 시각화 도우미를 한 번만 생성

#threshold = 100  # 제스처로 인식할 최소 이동 거리
vertical_threshold = 20
horizontal_threshold = 20

# --- 기능 함수들 ---

def minimize_window():
    """현재 활성화된 창을 최소화합니다."""
    try:
        active_window = gw.getActiveWindow()
        if active_window:
            active_window.minimize()
            print("기능: 창 최소화")
    except Exception as e:
        print(f"창 최소화 오류: {e}")

def toggle_maximize_window():
    """활성 창의 최대화/이전 크기 상태를 전환합니다."""
    try:
        active_window = gw.getActiveWindow()
        if active_window:
            if active_window.isMaximized:
                active_window.restore()
                print("기능: 창 이전 크기로")
            else:
                active_window.maximize()
                print("기능: 창 최대화")
    except Exception as e:
        print(f"최대화 전환 오류: {e}")

def next_page():
    """다음 페이지로 이동합니다 (Alt+Right Arrow 키 입력)."""
    pyautogui.hotkey('alt', 'right')
    print("기능: 다음 페이지")

def prev_page():
    """이전 페이지로 이동합니다 (Alt+Left Arrow 키 입력)."""
    pyautogui.hotkey('alt', 'left')
    print("기능: 이전 페이지")

def copy_action():
    """선택한 것을 복사합니다 (Ctrl+C 키 입력)."""
    pyautogui.hotkey('ctrl', 'c')
    print("기능: 복사")

def paste_action():
    """클립보드 내용을 붙여넣습니다 (Ctrl+V 키 입력)."""
    pyautogui.hotkey('ctrl', 'v')
    print("기능: 붙여넣기")

def close_window():
    """활성 창을 닫습니다 (Alt+F4 키 입력). 파일 탐색기 문제 해결 로직 포함."""
    try:
        active_window = gw.getActiveWindow()
        
        if active_window:
            active_window.close()
            print(f"기능: 창 닫기 ✅")
            # # 파일 탐색기 창 제목에 '파일 탐색기' 또는 'PC'가 포함되어 있는지 확인
            # if '파일 탐색기' in active_window.title or active_window.title.endswith('PC'):
            #     # 파일 탐색기: Ctrl+W가 현재 탭/창을 닫는 데 가장 안정적입니다.
            #     pyautogui.hotkey('ctrl', 'w')
            #     print("기능: 창 닫기 (Ctrl+W - 파일 탐색기) ✅")
            # else:
            #     # 💡 텔레그램, 그림판 등 대부분의 일반 창에 적용되는 가장 확실한 종료 방법
            #     active_window.close()
            #     print(f"기능: 창 닫기 ({active_window.title} 직접 종료) ✅")
                
    except Exception as e:
        # active_window가 None일 때 (예: 데스크톱만 보일 때) 또는 close() 실패 시 Fallback
        pyautogui.hotkey('alt', 'f4') 
        print(f"창 닫기 오류 발생, Alt+F4 시도: {e}")

# --- 제스처 인식 ---

def analyze_gesture():
    """기록된 제스처 포인트를 분석하고 해당 기능을 실행합니다."""
    #if len(gesture_points) < 5:  # 작은 움직임은 무시
    #    return

    start_x, start_y = gesture_points[0]
    end_x, end_y = gesture_points[-1]
    
    dx = end_x - start_x
    dy = end_y - start_y
    
    # threshold = 100  # 제스처로 인식할 최소 이동 거리

    print(f"제스처 분석: dx={dx}, dy={dy}")

    # 대각선 제스처를 먼저 확인
    # 오른쪽 위 -> 왼쪽 아래 (↘)
    # if dx < -threshold and dy > threshold:
    if dx < -horizontal_threshold and dy > vertical_threshold:
        minimize_window()
    # 왼쪽 아래 -> 오른쪽 위 (↗)
    # elif dx > threshold and dy < -threshold:
    elif dx > horizontal_threshold and dy < -vertical_threshold:
        toggle_maximize_window()
    # 그 다음 수평/수직 제스처 확인
    # 수평 움직임 (왼쪽 -> 오른쪽) (→)
    # elif dx > threshold and abs(dy) < threshold:
    elif dx > horizontal_threshold and abs(dy) < vertical_threshold:
        next_page()
    # 수평 움직임 (오른쪽 -> 왼쪽) (←)
    # elif dx < -threshold and abs(dy) < threshold:
    elif dx < -horizontal_threshold and abs(dy) < vertical_threshold:
        prev_page()
    # 수직 움직임 (아래 -> 위) (↑)
    # elif dy < -threshold and abs(dx) < threshold:
    elif dy < -vertical_threshold and abs(dx) < horizontal_threshold:
        copy_action()
    # 수직 움직임 (위 -> 아래) (↓)
    # elif dy > threshold and abs(dx) < threshold:
    elif dy > vertical_threshold and abs(dx) < horizontal_threshold:
        paste_action()
    # 오른쪽 아래 -> 왼쪽 위 (↖)
    elif dx < -horizontal_threshold and dy < -vertical_threshold:
        close_window()
    else:
        print(f"제스처가 인식되지 않았습니다. (dx: {dx}, dy: {dy})")


# --- 마우스 리스너 콜백 ---

def on_move(x, y):
    """마우스가 움직일 때 호출됩니다."""
    global gesture_points

    if is_right_button_pressed:
        gesture_points.append((x, y))
        # if visualizer:
        #     visualizer.draw_gesture(gesture_points)
        # GUI 업데이트는 스레드 안전한 after를 통해 예약
        # copy()를 사용하여 리스트 복사본을 전달하여 스레드 안전성 확보

        visualizer.root.after(0, lambda: visualizer.draw_gesture(gesture_points.copy()))

        # visualizer.root.after(0, lambda: visualizer.draw_gesture([(x, y)]))

def on_click(x, y, button, pressed):
    """마우스 버튼이 클릭될 때 호출됩니다."""
    global is_right_button_pressed, gesture_points, visualizer

    if button == mouse.Button.right:
        if pressed:
            is_right_button_pressed = True
            gesture_points = [(x, y)]
            print("마우스 오른쪽 버튼 누름. 제스처 기록 시작...")

            # # 메인 스레드에서 visualizer를 생성
            # visualizer = GestureVisualizer()
            
            # # 별도의 스레드에서 Tkinter 메인 루프를 실행
            # visualizer_thread = Thread(target=visualizer.run)
            # visualizer_thread.start()

            # GUI 업데이트는 스레드 안전한 after를 통해 예약
            visualizer.root.after(0, visualizer.show)
        else:
            is_right_button_pressed = False
            print("마우스 오른쪽 버튼 뗌. 제스처 분석...")
            
            # if visualizer:
            #     # Tkinter의 hide_and_destroy는 스레드 안전하지 않을 수 있으므로
            #     # root.after를 사용하여 메인 루프 스레드에서 실행하도록 예약합니다.
            #     visualizer.root.after(0, visualizer.hide_and_destroy)
            #     visualizer = None

            # GUI 업데이트는 스레드 안전한 after를 통해 예약
            visualizer.root.after(0, visualizer.hide)
            analyze_gesture()
            gesture_points = []

def on_scroll(x, y, dx, dy):
    """마우스 휠을 스크롤할 때 호출됩니다."""

    pass  # 이 프로젝트에서는 사용하지 않음

# --- 메인 실행 ---

def start_mouse_listener():
    """마우스 리스너를 시작합니다."""
    with mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll) as listener:
        listener.join()

if __name__ == "__main__":
    print("마우스 제스처 프로그램이 실행 중입니다...")
    print("마우스 오른쪽 버튼을 누른 상태로 제스처를 그려보세요.")

    # # 리스너 생성 및 시작
    # with mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll) as listener:
    #     listener.join()

    # 프로그램 종료 시 visualizer 정리
    atexit.register(visualizer.destroy)

    # 별도의 스레드에서 마우스 리스너 실행
    listener_thread = Thread(target=start_mouse_listener, daemon=True)
    listener_thread.start()

    # 메인 스레드에서 Tkinter GUI 실행
    visualizer.run()