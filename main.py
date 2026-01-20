import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QAction,
                             QHBoxLayout, QPushButton, QSlider, QLabel,
                             QFileDialog, QSplitter)
from PyQt5.QtCore import Qt, QTimer, QStandardPaths
from PyQt5.QtGui import QImage, QPixmap
import cv2
import logging
import json
from playlist_panel import PlaylistPanel
from m3u_panel import M3UPanel

# Try to import pygame for audio support
try:
    import pygame
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Warning: pygame not available. Audio playback will be disabled.")

class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.orientation() == Qt.Horizontal:
            x = event.x()
            w = max(1, self.width())
            ratio = x / w
            new_val = round(self.minimum() + ratio * (self.maximum() - self.minimum()))
            self.setValue(new_val)
            try:
                self.sliderMoved.emit(new_val)
            except Exception:
                pass
            try:
                self.sliderReleased.emit()
            except Exception:
                pass
        super().mousePressEvent(event)

class SettingStorage:
    def __init__(self, filename='settings.json'):
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        os.makedirs(config_dir, exist_ok=True)
        self.path = os.path.join(config_dir, filename)

    def save_state(self, state: dict):
        with open(self.path, "w", encoding="utf-8") as f:
            import json
            json.dump(state, f, ensure_ascii=False, indent=2)

    def load_state(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


class SimpleVideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.previous_volume = 100  # To store volume before muting

        # Set up logger to log to a file
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("vlc_tagger.log", encoding="utf-8"),
                logging.StreamHandler()
            ]
        )
        self.logger.debug('Initializing SimpleVideoPlayer')

        self.setWindowTitle("Simple Video Player (OpenCV)")
        self.setGeometry(100, 100, 1200, 800)

        # OpenCV video capture and playback state
        self.video_capture = None
        self.is_playing = False
        self.is_paused = False
        self.current_frame = 0
        self.total_frames = 0
        self.fps = 30
        self.current_file = None
        self.is_muted = False
        self.volume = 100

        # Initialize pygame for audio if available
        if AUDIO_AVAILABLE:
            try:
                pygame.mixer.init()
                self.logger.info('Pygame audio initialized')
            except Exception as e:
                self.logger.error(f'Failed to initialize pygame audio: {e}')

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create content frame with splitter for resizable panels
        content_splitter = QSplitter(Qt.Horizontal)

        # ==============================================================================================================
        # Create menu bar

        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')

        open_file_action = QAction('Open Video', self)
        open_file_action.triggered.connect(self.open_file)
        file_menu.addAction(open_file_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Playlist menu
        playlist_menu = menubar.addMenu("Playlist")

        select_folder_action = playlist_menu.addAction("Select Folder")
        select_folder_action.triggered.connect(PlaylistPanel.select_folder)
        playlist_menu.addAction(select_folder_action)

        load_m3u_action = playlist_menu.addAction("Load M3U/M3U8")
        load_m3u_action.triggered.connect(M3UPanel.load_m3u_file)
        playlist_menu.addAction(load_m3u_action)

        playlist_menu.addSeparator()

        clear_folder_action = playlist_menu.addAction("Clear Folder Playlist")
        clear_folder_action.triggered.connect(lambda: self.clear_playlist('folder'))
        playlist_menu.addAction(clear_folder_action)

        clear_m3u_action = playlist_menu.addAction("Clear M3U Playlist")
        clear_m3u_action.triggered.connect(lambda: self.clear_playlist('m3u'))
        playlist_menu.addAction(clear_m3u_action)

        #===============================================================================================================
        # Create video display widget (QLabel to show OpenCV frames)

        self.video_label = QLabel()
        self.video_label.setMinimumSize(800, 600)
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setScaledContents(False)
        content_splitter.addWidget(self.video_label)

        # ==============================================================================================================
        # Sidebar splitter for playlist panels

        sidebar_splitter = QSplitter(Qt.Vertical)
        sidebar_splitter.setChildrenCollapsible(False)

        # =============================================================================================================
        # Folder playlist panel (top half)

        self.playlist_panel = PlaylistPanel(None, self.play_file)
        sidebar_splitter.addWidget(self.playlist_panel)

        # =============================================================================================================
        # M3U playlist panel (bottom half)

        self.m3u_panel = M3UPanel(None, self.play_file)
        sidebar_splitter.addWidget(self.m3u_panel)

        # Set initial sizes for the panels
        sidebar_splitter.setSizes([200, 200])
        content_splitter.addWidget(sidebar_splitter)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(content_splitter)

        # Track which panel is currently active
        self.active_panel = 'folder'  # 'folder' or 'm3u'

        # Create controls frame
        controls_frame = QWidget()
        controls_layout = QHBoxLayout(controls_frame)


        # Open button
        self.open_button = QPushButton("Open Video")
        self.open_button.clicked.connect(self.open_file)
        controls_layout.addWidget(self.open_button)

        # Play/Pause button
        self.play_pause_button = QPushButton("Play")
        self.play_pause_button.clicked.connect(self.play_pause)
        controls_layout.addWidget(self.play_pause_button)

        # Stop button
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        controls_layout.addWidget(self.stop_button)

        # Previous Track button
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.previous_track)
        controls_layout.addWidget(self.prev_button)

        # Next Track button
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_track)
        controls_layout.addWidget(self.next_button)

        # Mute button
        self.mute_button = QPushButton("Mute")
        self.mute_button.clicked.connect(self.mute)
        controls_layout.addWidget(self.mute_button)

        # Volume controls
        volume_label = QLabel("Volume")
        controls_layout.addWidget(volume_label)

        self.volume_slider = ClickableSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.valueChanged.connect(self.set_volume)
        controls_layout.addWidget(self.volume_slider)

        time_label = QLabel("Time")
        controls_layout.addWidget(time_label)
        # Time bar (seek bar)
        self.time_slider = ClickableSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.setMinimumWidth(300)
        self.time_slider.sliderPressed.connect(self.on_seek_start)
        self.time_slider.sliderReleased.connect(self.on_seek_release)
        controls_layout.addWidget(self.time_slider)

        main_layout.addWidget(controls_frame)

        self.updating_slider = False
        self.seeking = False

        # Timer for updating video frames and time slider
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

        # Timer for updating time slider
        self.slider_timer = QTimer()
        self.slider_timer.timeout.connect(self.update_time_slider)
        self.slider_timer.start(100)

    def open_file(self):
        self.logger.debug('Open file dialog triggered')
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            "",
            "Video files (*.mp4 *.avi *.mkv);;All files (*.*)"
        )
        if file_path:
            self.logger.info(f'File selected: {file_path}')
            # Add to folder playlist
            self.playlist_panel.add_to_playlist(file_path)
            self.play_file(file_path)
        else:
            self.logger.info('No file selected')

    def play_file(self, file_path):
        """Play a specific file"""
        self.logger.info(f'Playing file: {file_path}')

        # Determine which panel contains the file and set it as active
        in_folder_panel = file_path in self.playlist_panel.playlist_files
        in_m3u_panel = file_path in self.m3u_panel.playlist_files

        if in_folder_panel and in_m3u_panel:
            # File is in both panels - use the currently active panel
            if self.active_panel == 'folder':
                self.playlist_panel.update_visual_selection(file_path)
                self.m3u_panel.set_current_file(file_path)  # Track internally only
                self.m3u_panel.clear_visual_selection()
            else:
                self.m3u_panel.update_visual_selection(file_path)
                self.playlist_panel.set_current_file(file_path)  # Track internally only
                self.playlist_panel.clear_visual_selection()
        elif in_folder_panel:
            # File only in folder panel
            self.active_panel = 'folder'
            self.playlist_panel.update_visual_selection(file_path)
            self.m3u_panel.clear_visual_selection()
            self.logger.debug('Set active panel to folder playlist')
        elif in_m3u_panel:
            # File only in M3U panel
            self.active_panel = 'm3u'
            self.m3u_panel.update_visual_selection(file_path)
            self.playlist_panel.clear_visual_selection()
            self.logger.debug('Set active panel to M3U playlist')
        else:
            # File not in either panel - clear both visual selections
            self.playlist_panel.clear_visual_selection()
            self.m3u_panel.clear_visual_selection()

        # Stop current playback if any
        if self.video_capture is not None:
            self.video_capture.release()
            self.timer.stop()
            if AUDIO_AVAILABLE and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()

        # Open the video file with OpenCV
        self.current_file = file_path
        self.video_capture = cv2.VideoCapture(file_path)

        if not self.video_capture.isOpened():
            self.logger.error(f'Failed to open video file: {file_path}')
            return

        # Get video properties
        self.total_frames = int(self.video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.video_capture.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30  # Default FPS if unable to get it

        self.current_frame = 0
        self.is_playing = True
        self.is_paused = False

        # Start playback timer
        interval = int(1000 / self.fps)
        self.timer.start(interval)

        # Try to play audio with pygame if available
        if AUDIO_AVAILABLE:
            try:
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.set_volume(self.volume / 100.0)
                pygame.mixer.music.play()
                self.logger.info('Audio playback started with pygame')
            except Exception as e:
                self.logger.warning(f'Could not play audio: {e}')

        self.play_pause_button.setText("Pause")
        self.logger.info(f'Video loaded: {self.total_frames} frames at {self.fps} fps')

    def play_pause(self):
        self.logger.debug('Play/Pause button pressed')
        if self.video_capture is None:
            self.logger.info('No video loaded')
            return

        if self.is_playing and not self.is_paused:
            self.logger.info('Pausing playback')
            self.is_paused = True
            self.timer.stop()
            if AUDIO_AVAILABLE and pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
            self.play_pause_button.setText("Play")
        else:
            self.logger.info('Starting/Resuming playback')
            self.is_paused = False
            self.is_playing = True
            interval = int(1000 / self.fps)
            self.timer.start(interval)
            if AUDIO_AVAILABLE:
                pygame.mixer.music.unpause()
            self.play_pause_button.setText("Pause")

    def stop(self):
        self.logger.debug('Stop button pressed')
        if self.video_capture is not None:
            self.timer.stop()
            self.is_playing = False
            self.is_paused = False
            self.current_frame = 0
            self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            if AUDIO_AVAILABLE and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            # Clear the display
            self.video_label.clear()
            self.video_label.setStyleSheet("background-color: black;")
            self.play_pause_button.setText("Play")
            self.time_slider.setValue(0)

    def previous_track(self):
        self.logger.debug('Previous track button pressed')

        # Try the active panel first, then fall back to the other panel
        prev_track = None
        if self.active_panel == 'folder':
            prev_track = self.playlist_panel.previous_track()
            if not prev_track:
                prev_track = self.m3u_panel.previous_track()
        else:
            prev_track = self.m3u_panel.previous_track()
            if not prev_track:
                prev_track = self.playlist_panel.previous_track()

        if prev_track:
            self.play_file(prev_track)
        else:
            self.logger.info('No previous track available')

    def next_track(self):
        self.logger.debug('Next track button pressed')

        # Try the active panel first, then fall back to the other panel
        next_track = None
        if self.active_panel == 'folder':
            next_track = self.playlist_panel.next_track()
            if not next_track:
                next_track = self.m3u_panel.next_track()
        else:
            next_track = self.m3u_panel.next_track()
            if not next_track:
                next_track = self.playlist_panel.next_track()

        if next_track:
            self.play_file(next_track)
        else:
            self.logger.info('No next track available')

    def mute(self):
        self.logger.debug('Mute button pressed')
        if not AUDIO_AVAILABLE:
            self.logger.warning('Audio not available')
            return

        self.is_muted = not self.is_muted
        if self.is_muted:
            self.logger.info('Audio muted')
            self.mute_button.setText("Unmute")
            self.previous_volume = self.volume
            self.volume = 0
            pygame.mixer.music.set_volume(0)
            self.volume_slider.setValue(0)
        else:
            self.logger.info('Audio unmuted')
            self.mute_button.setText("Mute")
            self.volume = self.previous_volume
            pygame.mixer.music.set_volume(self.volume / 100.0)
            self.volume_slider.setValue(self.previous_volume)


    def set_volume(self, value):
        if not AUDIO_AVAILABLE:
            return

        volume = int(value)
        self.volume = volume

        if value == 0:
            self.is_muted = True
            self.mute_button.setText("Unmute")
            self.logger.info('Audio muted via volume slider')
        else:
            self.is_muted = False
            self.mute_button.setText("Mute")

        self.logger.debug(f'Setting volume to {volume}')
        pygame.mixer.music.set_volume(volume / 100.0)
        self.logger.info(f'Volume set to {volume}')

    def on_seek_start(self):
        """Called when user starts dragging the time slider"""
        self.seeking = True

    def on_seek_release(self):
        """Called when user releases the time slider"""
        if self.video_capture is not None and self.total_frames > 0:
            value = self.time_slider.value()
            target_frame = int(float(value) / 100 * self.total_frames)
            self.logger.debug(f'Seeking to frame {target_frame}')
            self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            self.current_frame = target_frame

            # Seek audio if available
            if AUDIO_AVAILABLE and pygame.mixer.music.get_busy():
                target_time_sec = target_frame / self.fps
                try:
                    # pygame doesn't support seeking well, so we need to restart playback from the position
                    # This is a limitation of pygame - it doesn't support precise seeking
                    pygame.mixer.music.play(start=target_time_sec)
                    if self.is_paused:
                        pygame.mixer.music.pause()
                except Exception as e:
                    self.logger.warning(f'Could not seek audio: {e}')

        self.seeking = False

    def update_time_slider(self):
        """Update the time slider position based on current playback"""
        if self.video_capture is not None and self.total_frames > 0 and not self.seeking:
            pos = (self.current_frame / self.total_frames) * 100
            self.time_slider.setValue(int(pos))

    def update_frame(self):
        """Read and display the next frame from the video"""
        if self.video_capture is None or not self.is_playing or self.is_paused:
            return

        ret, frame = self.video_capture.read()

        if ret:
            # Convert the frame from BGR (OpenCV format) to RGB (Qt format)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Get frame dimensions
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w

            # Convert to QImage
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)

            # Scale the image to fit the label while maintaining aspect ratio
            scaled_pixmap = QPixmap.fromImage(qt_image).scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            # Display the frame
            self.video_label.setPixmap(scaled_pixmap)

            self.current_frame += 1
        else:
            # End of video reached
            self.logger.info('End of video reached')
            self.timer.stop()
            self.is_playing = False
            self.play_pause_button.setText("Play")

            # Check if we should play the next track
            next_track = None
            if self.active_panel == 'folder':
                next_track = self.playlist_panel.next_track()
                if not next_track:
                    next_track = self.m3u_panel.next_track()
            else:
                next_track = self.m3u_panel.next_track()
                if not next_track:
                    next_track = self.playlist_panel.next_track()

            if next_track:
                self.play_file(next_track)

    def clear_playlist(self, panel_type):
        """Clear the specified playlist panel"""
        if panel_type == 'folder':
            self.playlist_panel.playlist_box.clear()
            self.playlist_panel.playlist_files = []
            self.playlist_panel.current_index = -1
            self.logger.info('Cleared folder playlist')
        elif panel_type == 'm3u':
            self.m3u_panel.playlist_box.clear()
            self.m3u_panel.playlist_files = []
            self.m3u_panel.current_index = -1
            self.m3u_panel.playlist_name_label.setText("No playlist loaded")
            self.logger.info('Cleared M3U playlist')

    def closeEvent(self, event):
        """Handle window close event"""
        self.logger.info('Closing application, releasing resources')
        try:
            self.timer.stop()
            self.slider_timer.stop()
            if self.video_capture is not None:
                self.video_capture.release()
            if AUDIO_AVAILABLE:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception as e:
            self.logger.error(f'Error releasing resources: {e}')
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = SimpleVideoPlayer()
    player.show()
    sys.exit(app.exec_())
