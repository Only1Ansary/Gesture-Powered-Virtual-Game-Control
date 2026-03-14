import sys
import os
import subprocess
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QStackedWidget, QGraphicsDropShadowEffect, QFrame)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QColor, QPalette, QLinearGradient, QMovie, QPixmap

from tuio_listener import TUIOListener
from character_map import get_character, get_all_characters
from game_launcher import launch_game

REACTVISION_EXE = r"D:\HCI\reacTIVision-1.5.1-win64\reacTIVision.exe"
_A = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Assests")
MAIN_BK_GIF = os.path.join(_A, "bk gifs", "main bk.gif")
GAME_ICON = os.path.join(_A, "game icons", "Beat_Saber_logo.jpg")

class TuioQThread(QThread):
    marker_detected_signal = pyqtSignal(int)
    marker_rotated_signal = pyqtSignal(str, int)

    def __init__(self):
        super().__init__()
        self.listener = TUIOListener(
            on_marker_detected=self.on_marker_detected,
            on_marker_rotated=self.on_marker_rotated
        )

    def on_marker_detected(self, fiducial_id: int):
        self.marker_detected_signal.emit(fiducial_id)
        
    def on_marker_rotated(self, direction: str, fiducial_id: int):
        self.marker_rotated_signal.emit(direction, fiducial_id)

    def run(self):
        self.listener.start()
        self.exec_()

    def stop(self):
        self.listener.stop()
        self.quit()
        self.wait()


class WelcomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Background Label
        self.bg_label = QLabel(self)
        self.movie = QMovie(MAIN_BK_GIF)
        self.bg_label.setMovie(self.movie)
        self.bg_label.setScaledContents(True)
        self.movie.start()
        
        # Overlay Layout
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(0, 0, 0, 150);")
        layout = QVBoxLayout(self.overlay)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        # Title
        self.title_label = QLabel("GESTURE-POWERED VIRTUAL GAME CONTROL")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Bahnschrift", 36, QFont.Bold))
        self.title_label.setStyleSheet("color: white; letter-spacing: 2px; background: transparent;")

        # Subtitle
        self.subtitle_label = QLabel("Welcome, User!\nPlease sign in by holding a TUIO marker in front of the camera.")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setFont(QFont("Bahnschrift", 16))
        self.subtitle_label.setStyleSheet("color: #00B4D8; background: transparent;")

        # Cards Layout
        self.cards_title = QLabel("REGISTERED USERS")
        self.cards_title.setAlignment(Qt.AlignCenter)
        self.cards_title.setFont(QFont("Consolas", 14, QFont.Bold))
        self.cards_title.setStyleSheet("color: #AAAAAA; background: transparent; margin-top: 20px;")
        
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)
        cards_layout.setAlignment(Qt.AlignCenter)
        
        for cid, user in get_all_characters().items():
            card = QFrame()
            card.setFixedSize(140, 200)
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {user['bg_gradient'][0]};
                    border-bottom: 5px solid {user['theme_color']};
                }}
            """)
            c_layout = QVBoxLayout(card)
            
            # Avatar
            avatar_path = os.path.join(_A, "user icons", user.get("avatar", ""))
            av_lbl = QLabel()
            av_lbl.setFixedSize(90, 90)
            av_lbl.setScaledContents(True)
            av_lbl.setStyleSheet("background: transparent;")
            if os.path.exists(avatar_path):
                av_lbl.setPixmap(QPixmap(avatar_path))
            else:
                av_lbl.setText(user.get('icon_char', ''))
                av_lbl.setFont(QFont("Segoe UI", 48))
                av_lbl.setAlignment(Qt.AlignCenter)
            
            name_lbl = QLabel(user['name'])
            name_lbl.setFont(QFont("Bahnschrift", 16, QFont.Bold))
            name_lbl.setStyleSheet(f"color: white; background: transparent;")
            name_lbl.setAlignment(Qt.AlignCenter)
            
            marker_lbl = QLabel(f"MARKER #{cid}")
            marker_lbl.setFont(QFont("Consolas", 10, QFont.Bold))
            marker_lbl.setStyleSheet(f"color: {user['theme_color']}; background: transparent;")
            marker_lbl.setAlignment(Qt.AlignCenter)
            
            c_layout.addWidget(av_lbl, alignment=Qt.AlignCenter)
            c_layout.addWidget(marker_lbl)
            c_layout.addWidget(name_lbl)
            
            cards_layout.addWidget(card)

        # Blinking Status
        self.status_label = QLabel("● LISTENING FOR TUIO")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Consolas", 14, QFont.Bold))
        self.status_label.setStyleSheet("color: #00FF00; background: transparent; margin-top: 30px;")
        
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self.toggle_blink)
        self.blink_timer.start(650)
        self.is_green = True

        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addWidget(self.cards_title)
        layout.addLayout(cards_layout)
        layout.addWidget(self.status_label)
        
    def toggle_blink(self):
        self.is_green = not self.is_green
        color = "#00FF00" if self.is_green else "#004400"
        self.status_label.setStyleSheet(f"color: {color}; background: transparent; margin-top: 30px;")

    def resizeEvent(self, event):
        self.bg_label.setGeometry(self.rect())
        self.overlay.setGeometry(self.rect())
        super().resizeEvent(event)


class CharacterWelcomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Background Movie
        self.bg_label = QLabel(self)
        self.movie = QMovie()
        self.bg_label.setMovie(self.movie)
        self.bg_label.setScaledContents(True)

        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        self.layout = QVBoxLayout(self.overlay)
        self.layout.setAlignment(Qt.AlignCenter)
        self.layout.setSpacing(10)

        # Avatar
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(200, 200)
        self.avatar_label.setScaledContents(True)
        self.avatar_label.setStyleSheet("background: transparent;")
        
        self.welcome_label = QLabel("Welcome,")
        self.welcome_label.setFont(QFont("Bahnschrift", 36))
        self.welcome_label.setAlignment(Qt.AlignCenter)
        self.welcome_label.setStyleSheet("color: white; background: transparent;")

        self.name_label = QLabel("")
        self.name_label.setFont(QFont("Impact", 72, QFont.Bold))
        self.name_label.setAlignment(Qt.AlignCenter)
        
        self.status_label = QLabel()
        self.status_label.setFont(QFont("Consolas", 18))
        self.status_label.setAlignment(Qt.AlignCenter)

        # Instruction bar at the bottom
        self.info_layout = QHBoxLayout()
        self.left_label = QLabel("◄ ROTATE LEFT to return to Main Menu")
        self.left_label.setFont(QFont("Bahnschrift", 16, QFont.Bold))
        
        self.right_label = QLabel("ROTATE RIGHT to Launch Game ►")
        self.right_label.setFont(QFont("Bahnschrift", 16, QFont.Bold))
        
        self.info_layout.addWidget(self.left_label, alignment=Qt.AlignLeft)
        self.info_layout.addStretch()
        self.info_layout.addWidget(self.right_label, alignment=Qt.AlignRight)

        self.layout.addStretch()
        self.layout.addWidget(self.avatar_label, alignment=Qt.AlignCenter)
        self.layout.addWidget(self.welcome_label)
        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.status_label)
        self.layout.addStretch()
        self.layout.addLayout(self.info_layout)

    def set_character(self, character_data: dict, cid: int):
        gif_path = os.path.join(_A, "bk gifs", character_data.get("gif", ""))
        self.movie.setFileName(gif_path)
        self.movie.start()

        avatar_path = os.path.join(_A, "user icons", character_data.get("avatar", ""))
        if os.path.exists(avatar_path):
            self.avatar_label.setPixmap(QPixmap(avatar_path))
        else:
            self.avatar_label.setText(character_data.get("icon_char", ""))
            self.avatar_label.setFont(QFont("Segoe UI", 80))
            self.avatar_label.setStyleSheet(f"color: {character_data['theme_color']}; background: transparent;")
            self.avatar_label.setAlignment(Qt.AlignCenter)

        self.name_label.setText(character_data["name"])
        self.name_label.setStyleSheet(f"color: {character_data['theme_color']}; background: transparent;")
        
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setColor(QColor(character_data['glow_color']))
        self.name_label.setGraphicsEffect(glow)
        
        self.status_label.setText(f"TUIO marker #{cid} recognised")
        self.status_label.setStyleSheet(f"color: {character_data['glow_color']}; background: transparent;")

        self.left_label.setStyleSheet(f"color: white; background: {character_data['bg_gradient'][1]}; padding: 10px; border: 2px solid {character_data['theme_color']};")
        self.right_label.setStyleSheet(f"color: {character_data['bg_gradient'][0]}; background: {character_data['theme_color']}; padding: 10px;")

    def set_launching(self):
        self.status_label.setText("Launching game...")
        self.status_label.setStyleSheet("color: white; background: transparent;")

    def resizeEvent(self, event):
        self.bg_label.setGeometry(self.rect())
        self.overlay.setGeometry(self.rect())
        super().resizeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gesture Beat Saber Login")
        self.setMinimumSize(1024, 768)
        self.setStyleSheet("background-color: #000000;")

        self.launch_reactivision()

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.welcome_page = WelcomePage()
        self.character_page = CharacterWelcomePage()

        self.stack.addWidget(self.welcome_page)
        self.stack.addWidget(self.character_page)
        self.main_layout.addWidget(self.stack)

        self.stack.setCurrentWidget(self.welcome_page)
        self.is_logging_in = False
        self.current_character_name = ""

        self.tuio_thread = TuioQThread()
        self.tuio_thread.marker_detected_signal.connect(self.handle_marker_detected)
        self.tuio_thread.marker_rotated_signal.connect(self.handle_marker_rotated)
        self.tuio_thread.start()

    def launch_reactivision(self):
        if not os.path.exists(REACTVISION_EXE):
            print(f"[WARN] reacTIVision not found: {REACTVISION_EXE}")
            return
        try:
            # We want to launch it minimized without blocking
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
            subprocess.Popen([REACTVISION_EXE], cwd=os.path.dirname(REACTVISION_EXE), startupinfo=si)
            print("[INFO] reacTIVision launched (minimised).")
        except Exception as exc:
            print(f"[ERROR] Could not launch reacTIVision: {exc}")

    @pyqtSlot(int)
    def handle_marker_detected(self, fiducial_id: int):
        if self.is_logging_in:
            return 
        character_data = get_character(fiducial_id)
        if character_data:
            print(f"[GUI] Authenticated character ID {fiducial_id}: {character_data['name']}")
            self.transition_to_character_page(character_data, fiducial_id)

    @pyqtSlot(str, int)
    def handle_marker_rotated(self, direction: str, fiducial_id: int):
        if not self.is_logging_in:
            return
        character_data = get_character(fiducial_id)
        if not character_data or character_data['name'] != self.current_character_name:
            return

        if direction == "left":
            self.reset_to_welcome()
        elif direction == "right":
            self.character_page.set_launching()
            QApplication.processEvents()
            success = launch_game(self.current_character_name)
            if success:
                self.showMinimized()
            else:
                self.character_page.status_label.setText("Failed to find/launch game.exe")
                self.character_page.status_label.setStyleSheet("color: #FF3B3B; background: transparent;")
                QTimer.singleShot(4000, self.reset_to_welcome)

    def transition_to_character_page(self, character_data: dict, cid: int):
        self.is_logging_in = True
        self.current_character_name = character_data['name']
        self.character_page.set_character(character_data, cid)
        
        self.welcome_page.movie.stop()
        self.stack.setCurrentWidget(self.character_page)

    def reset_to_welcome(self):
        self.is_logging_in = False
        self.current_character_name = ""
        self.character_page.movie.stop()
        self.welcome_page.movie.start()
        self.stack.setCurrentWidget(self.welcome_page)

    def closeEvent(self, event):
        self.tuio_thread.stop()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.showFullScreen()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
