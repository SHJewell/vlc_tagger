import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QSlider, QLabel,
                             QFileDialog, QFrame)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import vlc
import logging
from playlist_panel import PlaylistPanel
from m3u_panel import M3UPanel

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

        self.setWindowTitle("Simple Video Player")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create content frame with horizontal layout
        content_frame = QWidget()
        content_layout = QHBoxLayout(content_frame)

        # Create video widget (VLC will embed here)
        self.video_widget = QWidget()
        self.video_widget.setMinimumSize(800, 600)
        self.video_widget.setStyleSheet("background-color: black;")
        content_layout.addWidget(self.video_widget, 1)

        # Create right sidebar for both playlist panels
        sidebar_frame = QWidget()
        sidebar_frame.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar_frame)

        # Folder playlist panel (top half)
        self.playlist_panel = PlaylistPanel(sidebar_frame, self.play_file)
        sidebar_layout.addWidget(self.playlist_panel, 1)

        # M3U playlist panel (bottom half)
        self.m3u_panel = M3UPanel(sidebar_frame, self.play_file)
        sidebar_layout.addWidget(self.m3u_panel, 1)

        content_layout.addWidget(sidebar_frame)
        main_layout.addWidget(content_frame)

        # Track which panel is currently active
        self.active_panel = 'folder'  # 'folder' or 'm3u'

        # Create controls frame
        controls_frame = QWidget()
        controls_layout = QHBoxLayout(controls_frame)

        # VLC instance and media player
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

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

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.valueChanged.connect(self.set_volume)
        controls_layout.addWidget(self.volume_slider)

        # Time bar (seek bar)
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.setMinimumWidth(300)
        self.time_slider.sliderPressed.connect(self.on_seek_start)
        self.time_slider.sliderReleased.connect(self.on_seek_release)
        controls_layout.addWidget(self.time_slider)

        main_layout.addWidget(controls_frame)

        self.updating_slider = False
        self.seeking = False

        # Timer for updating time slider
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time_slider)
        self.timer.start(500)

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

        # Set VLC to use the video widget
        if sys.platform.startswith('linux'):  # for Linux using the X Server
            self.player.set_xwindow(self.video_widget.winId())
        elif sys.platform == "win32":  # for Windows
            self.player.set_hwnd(self.video_widget.winId())
        elif sys.platform == "darwin":  # for MacOS
            self.player.set_nsobject(int(self.video_widget.winId()))

        media = self.instance.media_new(file_path)
        self.player.set_media(media)
        self.player.play()
        self.play_pause_button.setText("Pause")

    def play_pause(self):
        self.logger.debug('Play/Pause button pressed')
        is_playing = self.player.is_playing()
        if is_playing:
            self.logger.info('Pausing playback')
            self.player.pause()
            self.play_pause_button.setText("Play")
        else:
            self.logger.info('Starting playback')
            self.player.play()
            self.play_pause_button.setText("Pause")

    def stop(self):
        self.logger.debug('Stop button pressed')
        self.player.stop()
        self.play_pause_button.setText("Play")

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
        is_muted = self.player.audio_get_mute()
        self.player.audio_toggle_mute()
        if is_muted:
            self.logger.info('Audio unmuted')
            self.mute_button.setText("Mute")
            self.volume_slider.setValue(self.previous_volume)
        else:
            self.logger.info('Audio muted')
            self.mute_button.setText("Unmute")
            self.previous_volume = self.volume_slider.value()
            self.volume_slider.setValue(0)


    def set_volume(self, value):
        volume = int(value)

        if value == 0:
            self.player.audio_set_mute(True)
            self.mute_button.setText("Unmute")
            self.logger.info('Audio muted via volume slider')
        elif value != 0:
            self.player.audio_set_mute(False)
            self.mute_button.setText("Mute")

        self.logger.debug(f'Setting volume to {volume}')
        self.player.audio_set_volume(volume)
        self.logger.info(f'Volume set to {volume}')

    def on_seek_start(self):
        """Called when user starts dragging the time slider"""
        self.seeking = True

    def on_seek_release(self):
        """Called when user releases the time slider"""
        if self.player.get_length() > 0:
            value = self.time_slider.value()
            seek_time = int(float(value) / 100 * self.player.get_length())
            self.logger.debug(f'Seeking to {seek_time} ms')
            self.player.set_time(seek_time)
        self.seeking = False

    def update_time_slider(self):
        if self.player.get_length() > 0 and not self.updating_slider and not self.seeking:
            pos = self.player.get_time() / self.player.get_length() * 100
            self.time_slider.setValue(int(pos))

    def closeEvent(self, event):
        """Handle window close event"""
        self.logger.info('Closing application, releasing VLC player')
        try:
            self.timer.stop()
            self.player.stop()
            self.player.release()
            self.instance.release()
        except Exception as e:
            self.logger.error(f'Error releasing VLC resources: {e}')
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = SimpleVideoPlayer()
    player.show()
    sys.exit(app.exec_())
