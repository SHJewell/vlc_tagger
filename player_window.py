"""
Player Window - Displays video/audio player with controls
"""
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QSlider, QLabel, QAction, QFileDialog)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
import ctypes
import logging
import platform

# Import VLC for media playback
try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False
    vlc = None
    print("Warning: python-vlc not available. Media playback will be disabled.")


if VLC_AVAILABLE:
    # Module-level so the ctypes callback is never garbage-collected while
    # libVLC still holds a pointer to it
    @vlc.CallbackDecorators.LogCb
    def _vlc_log_cb(data, level, ctx, fmt, args):
        """Route libVLC's log stream into Python logging.

        libVLC normally writes straight to stderr, bypassing logging entirely.
        Levels: 0=debug, 2=notice, 3=warning, 4=error.
        """
        if level < 3:  # skip debug/notice noise
            return
        try:
            buf = ctypes.create_string_buffer(1024)
            ctypes.cdll.msvcrt.vsnprintf(buf, len(buf), fmt, ctypes.cast(args, ctypes.c_void_p))
            msg = buf.value.decode('utf-8', errors='replace')
        except Exception:
            msg = '<unformattable libVLC message>'
        logging.getLogger('libvlc').log(
            {3: logging.WARNING, 4: logging.ERROR}.get(level, logging.DEBUG), msg)


class ClickableSlider(QSlider):
    """Slider that allows clicking anywhere on the bar to jump to that position"""
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


class PlayerWindow(QMainWindow):
    """Player window with video/audio display and playback controls"""

    # Emitted from the libVLC event thread; queued to the Qt main thread
    media_ended = pyqtSignal()

    def __init__(self, file_window_callback=None, config_manager=None):
        super().__init__()
        
        self.logger = logging.getLogger(__name__)
        self.logger.debug('Initializing PlayerWindow')
        
        # Callback to notify file window of track changes
        self.file_window_callback = file_window_callback
        
        # Config manager
        self.config_manager = config_manager

        # VLC player state
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_media = None

        # Playback state
        self.is_playing = False
        self.is_paused = False
        self.current_file = None
        self.is_muted = False
        self.volume = 100
        self.previous_volume = 100
        self.shuffle_mode = False
        self.seeking = False
        self.autoplay_on_launch = False
        # One-shot guard: end-of-media can be reported by both the libVLC
        # event and the slider-timer fallback; only the first may act
        self._end_handled = False

        # Load saved volume from config
        if self.config_manager:
            self.volume = self.config_manager.get_volume()
            self.shuffle_mode = self.config_manager.get_shuffle_mode()

        self.setWindowTitle("Media Player")
        self.setGeometry(100, 100, 800, 700)
        
        self._setup_ui()

        # End-of-media is signalled from the libVLC event thread; force a
        # queued connection so _handle_media_end always runs on the Qt main
        # thread (calling into libVLC from its own event thread deadlocks)
        self.media_ended.connect(self._handle_media_end, Qt.QueuedConnection)

        # Timer for updating time slider
        self.slider_timer = QTimer()
        self.slider_timer.timeout.connect(self._update_time_slider)
        self.slider_timer.start(100)

        if self.config_manager:
            self.autoplay_on_launch = self.config_manager.get_autoplay_on_launch()
        
        self.logger.debug('PlayerWindow initialized')
    
    def _setup_ui(self):
        """Setup the user interface"""
        # Create menu bar
        self._create_menus()

        # Initialize VLC if available
        if VLC_AVAILABLE:
            try:
                # Force the Direct3D9 output instead of the default D3D11 one.
                # D3D11's vout close path calls DWM's SetThumbnailClip, which
                # returns 0x800706f4 (invalid window handle) during our rapid
                # stop/set_media/play track transitions and deadlocks libVLC's
                # render thread -- this is what causes the app to hang instead
                # of advancing to the next track (see log's SetThumbNailClip
                # errors immediately preceding every unclean restart).
                self.vlc_instance = vlc.Instance('--no-xlib', '--vout=direct3d9', '--aout=directsound')
                self.vlc_instance.log_set(_vlc_log_cb, None)
                self.vlc_player = self.vlc_instance.media_player_new()
                self.logger.info('VLC player initialized')
            except Exception as e:
                self.logger.error(f'Failed to initialize VLC player: {e}')

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Video display area
        self.video_label = QLabel()
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setScaledContents(False)
        main_layout.addWidget(self.video_label, 1)
        
        # Set VLC video output to the widget
        if self.vlc_player:
            if platform.system() == "Windows":
                self.vlc_player.set_hwnd(int(self.video_label.winId()))
            elif platform.system() == "Darwin":  # macOS
                self.vlc_player.set_nsobject(int(self.video_label.winId()))
            else:  # Linux
                self.vlc_player.set_xwindow(int(self.video_label.winId()))

        # Time slider
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        time_layout.addWidget(self.current_time_label)
        
        self.time_slider = ClickableSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 1000)
        self.time_slider.sliderPressed.connect(self._on_seek_start)
        self.time_slider.sliderReleased.connect(self._on_seek_release)
        time_layout.addWidget(self.time_slider, 1)
        
        self.total_time_label = QLabel("00:00")
        time_layout.addWidget(self.total_time_label)

        self.updating_slider = False
        self.seeking = False

        
        main_layout.addLayout(time_layout)
        
        # Control buttons
        controls_layout = QHBoxLayout()
        
        # Previous button
        self.prev_button = QPushButton("⏮ Previous")
        self.prev_button.clicked.connect(self.previous_track)
        controls_layout.addWidget(self.prev_button)
        
        # Play/Pause button
        self.play_pause_button = QPushButton("▶ Play")
        self.play_pause_button.clicked.connect(self.play_pause)
        controls_layout.addWidget(self.play_pause_button)
        
        # Stop button
        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.clicked.connect(self.stop)
        controls_layout.addWidget(self.stop_button)
        
        # Next button
        self.next_button = QPushButton("Next ⏭")
        self.next_button.clicked.connect(self.next_track)
        controls_layout.addWidget(self.next_button)
        
        # Shuffle button
        self.shuffle_button = QPushButton("🔀 Shuffle")
        self.shuffle_button.setCheckable(True)
        self.shuffle_button.setChecked(self.shuffle_mode)  # Use saved shuffle mode
        self.shuffle_button.clicked.connect(self._toggle_shuffle)
        controls_layout.addWidget(self.shuffle_button)
        
        controls_layout.addStretch()
        
        # Volume controls
        volume_label = QLabel("🔊")
        controls_layout.addWidget(volume_label)
        
        self.volume_slider = ClickableSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.volume)  # Use saved volume
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.valueChanged.connect(self._set_volume)
        controls_layout.addWidget(self.volume_slider)
        
        # Mute button
        self.mute_button = QPushButton("Mute")
        self.mute_button.clicked.connect(self._toggle_mute)
        controls_layout.addWidget(self.mute_button)
        
        main_layout.addLayout(controls_layout)
    
    def _create_menus(self):
        """Create menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        open_action = QAction('Open File...', self)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Playback menu
        playback_menu = menubar.addMenu('Playback')
        
        play_action = QAction('Play/Pause', self)
        play_action.setShortcut('Space')
        play_action.triggered.connect(self.play_pause)
        playback_menu.addAction(play_action)
        
        stop_action = QAction('Stop', self)
        stop_action.triggered.connect(self.stop)
        playback_menu.addAction(stop_action)
        
        playback_menu.addSeparator()
        
        prev_action = QAction('Previous', self)
        prev_action.setShortcut('Left')
        prev_action.triggered.connect(self.previous_track)
        playback_menu.addAction(prev_action)
        
        next_action = QAction('Next', self)
        next_action.setShortcut('Right')
        next_action.triggered.connect(self.next_track)
        playback_menu.addAction(next_action)

        self.autoplay_action = QAction('Autoplay on Launch', self)
        self.autoplay_action.setCheckable(True)
        self.autoplay_action.setChecked(self.autoplay_on_launch)
        self.autoplay_action.triggered.connect(self._toggle_autoplay_on_launch)
        playback_menu.addAction(self.autoplay_action)
    
    def _open_file(self):
        """Open file dialog to select a media file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Media File",
            "",
            "Media files (*.mp4 *.avi *.mkv *.mov *.mp3 *.wav *.flac);;All files (*.*)"
        )
        if file_path:
            self.play_file(file_path)
    
    def play_file(self, file_path, autoplay=True):
        """Play a specific file"""
        if not VLC_AVAILABLE or not self.vlc_player:
            self.logger.error('VLC player not available')
            return

        self.logger.info(f'Playing file: {file_path}')
        
        # Stop current playback if any
        self._stop_playback()

        self.current_file = file_path
        
        # Save current file to config
        if self.config_manager:
            self.config_manager.set_current_file(file_path, auto_save=True)

        try:
            # Create VLC media
            self.vlc_media = self.vlc_instance.media_new(file_path)
            self.vlc_player.set_media(self.vlc_media)

            # Re-arm the end-of-media guard for the new track
            self._end_handled = False

            # Attach end-of-media event (store manager to detach later)
            try:
                self._vlc_event_manager = self.vlc_player.event_manager()
                # Avoid attaching multiple handlers if already attached
                self._vlc_event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_media_end)
            except Exception as e:
                self.logger.warning(f'Could not attach VLC end event: {e}')

            self._update_media_info()

            # Set volume
            self.vlc_player.audio_set_volume(self.volume)

            # Only start playback if autoplay is True
            if autoplay:
                self.vlc_player.play()
                self.is_playing = True
                self.is_paused = False
                self.play_pause_button.setText("⏸ Pause")
            else:
                # Load but don't play
                self.is_playing = False
                self.is_paused = False
                self.play_pause_button.setText("▶ Play")

            # Notify file window
            if self.file_window_callback:
                self.file_window_callback('file_changed', file_path)

        except Exception as e:
            self.logger.error(f'Failed to play file: {e}')
            self._stop_playback()

    def _update_media_info(self):
        """Update media information after loading"""
        if self.vlc_player and self.vlc_media:
            # Parse media to get duration
            self.vlc_media.parse()

            # Get duration in milliseconds
            duration_ms = self.vlc_media.get_duration()
            if duration_ms > 0:
                duration_sec = duration_ms / 1000.0
                self.total_time_label.setText(self._format_time(duration_sec))
            else:
                self.total_time_label.setText("--:--")

    def _on_media_end(self, event):
        """Called by libVLC on its event thread when media playback ends.

        Must not touch Qt widgets or call back into libVLC here — only emit
        the signal, which is queued to the main thread.
        """
        self.logger.info('Media playback ended')
        self.media_ended.emit()

    def _handle_media_end(self):
        """Handle end-of-media actions on the Qt thread"""
        if self._end_handled:
            return
        self._end_handled = True

        self.is_playing = False
        self.play_pause_button.setText("▶ Play")

        # Stop current playback resources (detaches events)
        self._stop_playback()

        # Auto-play next track via file window
        QTimer.singleShot(100, self.next_track)

    def _stop_playback(self):
        """Stop all playback and detach events"""
        if self.vlc_player:
            try:
                self.vlc_player.stop()
            except Exception:
                pass

        # Detach previously attached end event to avoid duplicate callbacks
        try:
            if hasattr(self, '_vlc_event_manager') and self._vlc_event_manager:
                try:
                    self._vlc_event_manager.event_detach(vlc.EventType.MediaPlayerEndReached)
                except Exception:
                    pass
                self._vlc_event_manager = None
        except Exception:
            pass

        self.is_playing = False
        self.is_paused = False
        self.current_file = None

    def play_pause(self):
        """Toggle play/pause"""
        if not self.vlc_player or self.current_file is None:
            return
        
        if self.is_playing and not self.is_paused:
            # Pause
            self.vlc_player.pause()
            self.is_paused = True
            self.play_pause_button.setText("▶ Play")
            self.logger.info('Paused')
        else:
            # Play/Resume
            if self.is_paused:
                self.vlc_player.pause()  # Toggle pause off
            else:
                self.vlc_player.play()
            self.is_paused = False
            self.is_playing = True
            self.play_pause_button.setText("⏸ Pause")
            self.logger.info('Playing')
    
    def stop(self):
        """Stop playback"""
        self._stop_playback()

        self.video_label.clear()
        self.video_label.setStyleSheet("background-color: black;")
        self.play_pause_button.setText("▶ Play")
        self.time_slider.setValue(0)
        self.current_time_label.setText("00:00")
        self.total_time_label.setText("00:00")
        self.logger.info('Stopped')
    
    def previous_track(self):
        """Request previous track from file window"""
        if self.file_window_callback:
            self.file_window_callback('previous', None)
    
    def next_track(self):
        """Request next track from file window"""
        if self.file_window_callback:
            self.file_window_callback('next', None)
    
    def _toggle_shuffle(self):
        """Toggle shuffle mode"""
        self.shuffle_mode = self.shuffle_button.isChecked()

        # Save shuffle mode to config
        if self.config_manager:
            self.config_manager.set_shuffle_mode(self.shuffle_mode, auto_save=True)

        if self.file_window_callback:
            self.file_window_callback('shuffle', self.shuffle_mode)
        self.logger.info(f'Shuffle mode: {self.shuffle_mode}')
    
    def _toggle_mute(self):
        """Toggle mute"""
        if not self.vlc_player:
            return

        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mute_button.setText("Unmute")
            self.vlc_player.audio_set_mute(True)
        else:
            self.mute_button.setText("Mute")
            self.vlc_player.audio_set_mute(False)

        self.logger.info(f'Mute: {self.is_muted}')

    def _toggle_autoplay_on_launch(self):
        """Toggle autoplay on launch"""
        self.autoplay_on_launch = not self.autoplay_on_launch
        if self.config_manager:
            self.config_manager.set_autoplay_on_launch(self.autoplay_on_launch, auto_save=True)

    def _set_volume(self, value):
        """Set volume level"""
        self.volume = int(value)

        if value == 0:
            self.is_muted = True
            self.mute_button.setText("Unmute")
        else:
            self.is_muted = False
            self.mute_button.setText("Mute")
        
        # Apply volume to VLC player
        if self.vlc_player:
            self.vlc_player.audio_set_volume(self.volume)

        # Save volume to config
        if self.config_manager:
            self.config_manager.set_volume(self.volume, auto_save=True)

        self.logger.debug(f'Volume set to: {self.volume}')

    def reload_from_config(self):
        """Re-apply settings after a profile switch.

        Stops playback and syncs volume/shuffle/autoplay to the new profile.
        The caller (VLCTaggerApp.apply_profile) restores the playlist and
        current file afterwards, inside config_manager.applying().
        """
        if not self.config_manager:
            return

        self.stop()

        self.volume = self.config_manager.get_volume()
        self.volume_slider.setValue(self.volume)

        self.shuffle_mode = self.config_manager.get_shuffle_mode()
        self.shuffle_button.setChecked(self.shuffle_mode)
        if self.file_window_callback:
            self.file_window_callback('shuffle', self.shuffle_mode)

        self.autoplay_on_launch = self.config_manager.get_autoplay_on_launch()
        self.autoplay_action.setChecked(self.autoplay_on_launch)

        self.logger.info('Player settings reloaded from config')

    def _on_seek_start(self):
        """Called when user starts seeking"""
        self.seeking = True
    
    def _on_seek_release(self):
        """Called when user releases seek slider"""
        if not self.vlc_player:
            return

        value = self.time_slider.value()
        position = value / 1000.0  # VLC uses 0.0 to 1.0

        self.vlc_player.set_position(position)
        self.seeking = False
        self.logger.debug(f'Seeked to position: {position}')

    def _update_time_slider(self):
        """Update time slider position and fallback-check for ended state"""
        if not self.vlc_player or self.seeking:
            return

        # Get current position (0.0 to 1.0)
        try:
            position = self.vlc_player.get_position()
            if position >= 0:
                self.time_slider.setValue(int(position * 1000))
        except Exception:
            position = -1

        # Get current time in milliseconds
        try:
            current_time_ms = self.vlc_player.get_time()
            if current_time_ms >= 0:
                current_seconds = current_time_ms / 1000.0
                self.current_time_label.setText(self._format_time(current_seconds))
        except Exception:
            pass

        # Update total time if not set yet
        try:
            if self.total_time_label.text() in ["--:--", "00:00"]:
                duration_ms = self.vlc_player.get_length()
                if duration_ms > 0:
                    duration_sec = duration_ms / 1000.0
                    self.total_time_label.setText(self._format_time(duration_sec))
        except Exception:
            pass

        # Fallback: check VLC player state for Ended
        try:
            if (not self._end_handled and VLC_AVAILABLE and self.vlc_player
                    and self.vlc_player.get_state() == vlc.State.Ended):
                QTimer.singleShot(0, self._handle_media_end)
        except Exception:
            pass

    def _format_time(self, seconds):
        """Format seconds as MM:SS"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
    
    def closeEvent(self, event):
        """Handle window close"""
        self.logger.info('Closing player window')

        # Save window position
        if self.config_manager:
            geometry = self.geometry()
            self.config_manager.set_window_position(
                'player',
                geometry.x(), geometry.y(),
                geometry.width(), geometry.height(),
                auto_save=True
            )

        self.slider_timer.stop()

        # Stop all playback
        self._stop_playback()

        event.accept()
