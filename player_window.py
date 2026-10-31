"""
Player Window - Displays video/audio player with controls
"""
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QSlider, QLabel, QAction, QFileDialog,
                             QApplication)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
import ctypes
import logging
import os
import platform

import app_registry
import instance

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
        Levels: 0=debug, 1=info, 2=notice, 3=warning, 4=error.
        """
        try:
            buf = ctypes.create_string_buffer(1024)
            ctypes.cdll.msvcrt.vsnprintf(buf, len(buf), fmt, ctypes.cast(args, ctypes.c_void_p))
            msg = buf.value.decode('utf-8', errors='replace')
        except Exception:
            msg = '<unformattable libVLC message>'

        # Module-loader messages ("using <module> module", "looking for
        # video/audio output module...") are logged below the notice level,
        # so the normal cutoff below would hide them -- but they're the only
        # way to see which vout/aout backend libVLC actually picked (e.g.
        # whether --vout=direct3d9 was honored or it fell back to direct3d11).
        # Surface them regardless of level; this is cheap since they're rare.
        is_module_selection = level < 2 and any(
            kw in msg for kw in ('vout', 'aout', 'video output module', 'audio output module')
        )

        if level < 2 and not is_module_selection:  # Skip debug/info noise
            return

        # Skip expected h264 frame decode warnings during transitions
        if any(skip in msg for skip in
               ['get_buffer() failed', 'thread_get_buffer', 'decode_slice_header', 'no frame']):
            return

        logging.getLogger('libvlc').log(
            {3: logging.WARNING, 4: logging.ERROR}.get(level, logging.DEBUG), msg)


# Files with these extensions have no picture, so the video area starts collapsed
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.flac', '.ogg', '.oga', '.opus', '.m4a',
                    '.aac', '.wma', '.aiff', '.aif', '.alac', '.ape', '.mka')


def is_audio_file(path):
    return bool(path) and os.path.splitext(path)[1].lower() in AUDIO_EXTENSIONS


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
    media_error = pyqtSignal()
    media_playing = pyqtSignal()

    # Stop auto-advancing after this many unplayable files in a row, so a
    # playlist of broken files (esp. in shuffle, which never ends) can't
    # skip forever
    MAX_CONSECUTIVE_ERRORS = 5

    # libVLC events attached per track in play_file, detached in _stop_playback
    _VLC_EVENT_NAMES = ('MediaPlayerEndReached', 'MediaPlayerEncounteredError',
                        'MediaPlayerPlaying')

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
        # True after a stop/end: the loaded file's events are detached, so
        # Play must reload it via play_file rather than just resume
        self._needs_reload = False
        # Set when the window is closed / after a restore (see _rebuild_video_output)
        self._rebuild_vout_on_show = False
        self._seek_on_resume = False
        # Unplayable files in a row; reset once a track actually plays
        self._consecutive_errors = 0
        # Window height to return to when the video area is expanded again
        self._expanded_height = None

        # Load saved volume from config
        if self.config_manager:
            self.volume = self.config_manager.get_volume()
            self.shuffle_mode = self.config_manager.get_shuffle_mode()

        # The playlist panel keeps its own shuffle flag; sync it at launch or
        # the button can show shuffle on while tracks play in order
        if self.file_window_callback:
            self.file_window_callback('shuffle', self.shuffle_mode)

        self.setWindowTitle(f"Media Player{instance.title_suffix()}")
        self.setGeometry(100, 100, 800, 700)
        
        self._setup_ui()

        # End-of-media is signalled from the libVLC event thread; force a
        # queued connection so _handle_media_end always runs on the Qt main
        # thread (calling into libVLC from its own event thread deadlocks)
        self.media_ended.connect(self._handle_media_end, Qt.QueuedConnection)
        self.media_error.connect(self._handle_media_error, Qt.QueuedConnection)
        self.media_playing.connect(self._handle_media_playing, Qt.QueuedConnection)

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
        # A checkbox glyph in the label shows the state; the checked-button
        # shading alone is too subtle in dark mode
        self.shuffle_button = QPushButton()
        self.shuffle_button.setCheckable(True)
        self.shuffle_button.toggled.connect(self._update_shuffle_text)
        self.shuffle_button.setChecked(self.shuffle_mode)  # Use saved shuffle mode
        self._update_shuffle_text(self.shuffle_mode)
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
        # Persist only once the drag ends, not on every step
        self.volume_slider.sliderReleased.connect(self._save_volume)
        controls_layout.addWidget(self.volume_slider)
        
        # Mute button
        self.mute_button = QPushButton("Mute")
        self.mute_button.clicked.connect(self._toggle_mute)
        controls_layout.addWidget(self.mute_button)

        # Collapse/expand the video area
        self.video_toggle_button = QPushButton()
        self.video_toggle_button.setCheckable(True)
        self.video_toggle_button.setChecked(True)
        self.video_toggle_button.clicked.connect(self.set_video_visible)
        controls_layout.addWidget(self.video_toggle_button)
        self._update_video_toggle_text()

        main_layout.addLayout(controls_layout)
        # Keeps the controls packed at the top when the video is collapsed
        main_layout.addStretch()
    
    def _create_menus(self):
        """Create menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        open_action = QAction('Open File...', self)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)
        
        self.restore_playlist_action = QAction('Restore Playlist Window', self)
        self.restore_playlist_action.triggered.connect(self._restore_playlist_window)
        file_menu.addAction(self.restore_playlist_action)
        file_menu.aboutToShow.connect(self._update_restore_action)

        file_menu.addSeparator()

        # Exit quits the whole app; closing the window with X only hides it
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(QApplication.closeAllWindows)
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

        # View menu (dark mode is app-wide; both windows' items stay in sync)
        view_menu = menubar.addMenu('View')
        self.dark_mode_action = QAction('Dark Mode', self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(
            bool(self.config_manager and self.config_manager.get_dark_mode()))
        self.dark_mode_action.triggered.connect(self._toggle_dark_mode)
        view_menu.addAction(self.dark_mode_action)

        self.show_video_action = QAction('Show Video', self)
        self.show_video_action.setCheckable(True)
        self.show_video_action.setChecked(True)
        self.show_video_action.setShortcut('V')
        self.show_video_action.triggered.connect(self.set_video_visible)
        view_menu.addAction(self.show_video_action)
    
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

        # Reopen the player if it was closed (files loaded without autoplay,
        # e.g. on a profile switch, don't pop it open)
        if autoplay and not self.isVisible():
            self.bring_to_front()

        # Stop current playback if any
        self._stop_playback()
        self._seek_on_resume = False  # new file gets a fresh video output

        self.current_file = file_path

        # Collapse the video area for audio, expand it for video
        self.set_video_visible(not is_audio_file(file_path), reattach=False)

        # Save current file to config
        if self.config_manager:
            self.config_manager.set_current_file(file_path, auto_save=True)

        try:
            # Create VLC media
            self.logger.debug('transition: calling media_new()')
            old_media = self.vlc_media
            self.vlc_media = self.vlc_instance.media_new(file_path)
            self.logger.debug('transition: calling set_media()')
            self.vlc_player.set_media(self.vlc_media)
            self.logger.debug('transition: set_media() returned')

            # Release the previous media now that the player no longer references it
            if old_media is not None:
                old_media.release()

            # Re-arm the end-of-media guard for the new track
            self._end_handled = False

            # Attach end/error/playing events (store manager to detach later)
            try:
                self._vlc_event_manager = self.vlc_player.event_manager()
                handlers = (self._on_media_end, self._on_media_error, self._on_media_playing)
                for name, handler in zip(self._VLC_EVENT_NAMES, handlers):
                    self._vlc_event_manager.event_attach(getattr(vlc.EventType, name), handler)
            except Exception as e:
                self.logger.warning(f'Could not attach VLC events: {e}')
            self._needs_reload = False

            self._update_media_info()

            # Set volume
            self.vlc_player.audio_set_volume(self.volume)

            # Only start playback if autoplay is True
            if autoplay:
                self.logger.debug('transition: calling vlc_player.play()')
                self.vlc_player.play()
                self.logger.debug('transition: vlc_player.play() returned')
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
            # Parse in the background (local files only, never network) so a
            # slow drive or http entry can't block the UI; _update_time_slider
            # fills in the duration once it's known
            self.total_time_label.setText("--:--")
            try:
                self.vlc_media.parse_with_options(vlc.MediaParseFlag.local, 0)
            except Exception as e:
                self.logger.debug(f'Background parse not started: {e}')

    def _on_media_end(self, event):
        """Called by libVLC on its event thread when media playback ends.

        Must not touch Qt widgets or call back into libVLC here — only emit
        the signal, which is queued to the main thread.
        """
        self.logger.info('Media playback ended')
        self.media_ended.emit()

    def _on_media_error(self, event):
        """libVLC event thread: the current file couldn't be played"""
        self.media_error.emit()

    def _on_media_playing(self, event):
        """libVLC event thread: playback actually started"""
        self.media_playing.emit()

    def _handle_media_playing(self):
        """A track played successfully, so reset the bad-file streak"""
        self._consecutive_errors = 0

    def _handle_media_error(self):
        """Skip an unplayable file, unless too many have failed in a row"""
        if self._end_handled:
            return

        self._consecutive_errors += 1
        self.logger.warning(
            f'Could not play file ({self._consecutive_errors} in a row): {self.current_file}')

        if self._consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
            self.logger.error(
                f'{self._consecutive_errors} files in a row failed to play; '
                'stopping auto-advance')
            self._end_handled = True
            self._stop_playback()
            self.play_pause_button.setText("▶ Play")
            return

        # Same path as a normal end of track: stop, then Next after 100ms
        self._handle_media_end()

    def _handle_media_end(self):
        """Handle end-of-media actions on the Qt thread"""
        if self._end_handled:
            return
        self._end_handled = True

        self.is_playing = False
        self.play_pause_button.setText("▶ Play")

        # Stop current playback resources (detaches events)
        self.logger.debug('media-end: calling _stop_playback()')
        self._stop_playback()
        self.logger.debug('media-end: _stop_playback() returned, scheduling next_track')

        # Auto-play next track via file window
        QTimer.singleShot(100, self.next_track)

    def _stop_playback(self):
        """Stop all playback and detach events"""
        if self.vlc_player:
            try:
                self.logger.debug('transition: calling vlc_player.stop()')
                self.vlc_player.stop()
                self.logger.debug('transition: vlc_player.stop() returned')
            except Exception:
                pass

        # Detach previously attached events to avoid duplicate callbacks
        try:
            if hasattr(self, '_vlc_event_manager') and self._vlc_event_manager:
                self.logger.debug('transition: calling event_detach()')
                for name in self._VLC_EVENT_NAMES:
                    try:
                        self._vlc_event_manager.event_detach(getattr(vlc.EventType, name))
                    except Exception:
                        pass
                self.logger.debug('transition: event_detach() returned')
                self._vlc_event_manager = None
        except Exception:
            pass

        self.is_playing = False
        self.is_paused = False
        # current_file is kept (it's the last loaded file) so Play can
        # restart it; events are detached, so it must go through play_file
        self._needs_reload = True

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
        elif self._needs_reload:
            # Stopped or ended: reload so events and the end guard are re-armed
            self.play_file(self.current_file)
        else:
            # Play/Resume
            if self.is_paused:
                self.vlc_player.pause()  # Toggle pause off
                if self._seek_on_resume:
                    # After a window restore the video stays blank until a
                    # seek; seeking to the current time kicks it back on
                    self._seek_on_resume = False
                    self.vlc_player.set_time(self.vlc_player.get_time())
            else:
                # Loaded without autoplay; already set up, just start it
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
    
    def _update_shuffle_text(self, checked):
        self.shuffle_button.setText(("☑" if checked else "☐") + " Shuffle")

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

    def set_video_visible(self, visible, reattach=True):
        """Collapse or expand the video area, shrinking/growing the window to fit.

        reattach=False skips rebuilding the video output on expand (used when
        a new file is about to load, which gets a fresh output anyway).
        """
        visible = bool(visible)
        self.show_video_action.setChecked(visible)
        self.video_toggle_button.setChecked(visible)
        self._update_video_toggle_text()
        # isHidden() is the label's own state; isVisible() would also be
        # False whenever the whole window is closed
        if visible != self.video_label.isHidden():
            return

        if visible:
            self.video_label.show()
            height = max(self._expanded_height or 0, self.minimumSizeHint().height())
            self.resize(self.width(), height)
            if reattach and self.isVisible():
                # The video output may have been torn down while hidden
                QTimer.singleShot(0, self._reattach_video_after_expand)
        else:
            self._expanded_height = self.height()
            self.video_label.hide()
            # Recompute the layouts now so the size hint no longer includes
            # the video's minimum size, then shrink to just the controls
            self.centralWidget().layout().activate()
            self.layout().invalidate()
            self.layout().activate()
            self.resize(self.width(), self.minimumSizeHint().height())

    def _reattach_video_after_expand(self):
        self._rebuild_video_output()
        # A playing video stays blank until a seek; a paused one is handled
        # on resume (see play_pause)
        if self._seek_on_resume and self.is_playing and not self.is_paused:
            self._seek_on_resume = False
            self.vlc_player.set_time(self.vlc_player.get_time())

    def _update_video_toggle_text(self):
        shown = self.video_toggle_button.isChecked()
        self.video_toggle_button.setText("▲ Hide Video" if shown else "▼ Show Video")

    def _toggle_dark_mode(self, enabled):
        app = app_registry.get('app')
        if app:
            app.set_dark_mode(enabled)

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

        # Update config in memory; written to disk by _save_volume on release
        if self.config_manager:
            self.config_manager.set_volume(self.volume, auto_save=False)

        self.logger.debug(f'Volume set to: {self.volume}')

    def _save_volume(self):
        """Write the volume to disk once the slider is released"""
        if self.config_manager:
            self.config_manager.save()

    def reload_from_config(self):
        """Re-apply settings after a profile switch.

        Stops playback and syncs volume/shuffle/autoplay to the new profile.
        The caller (VLCTaggerApp.apply_profile) restores the playlist and
        current file afterwards, inside config_manager.applying().
        """
        if not self.config_manager:
            return

        self.stop()
        # Forget the old profile's track so Play can't restart it
        self.current_file = None

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
                # Not playing yet (e.g. loaded without autoplay or after
                # Stop): fall back to the background parse result
                if duration_ms <= 0 and self.vlc_media and self.current_file:
                    duration_ms = self.vlc_media.get_duration()
                if duration_ms > 0:
                    duration_sec = duration_ms / 1000.0
                    self.total_time_label.setText(self._format_time(duration_sec))
        except Exception:
            pass

        # Fallback: check VLC player state for Ended/Error in case the event
        # was missed (both handlers ignore repeats via _end_handled)
        try:
            if not self._end_handled and VLC_AVAILABLE and self.vlc_player:
                state = self.vlc_player.get_state()
                if state == vlc.State.Ended:
                    QTimer.singleShot(0, self._handle_media_end)
                elif state == vlc.State.Error:
                    QTimer.singleShot(0, self._handle_media_error)
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
            # Save the full-size height even while the video is collapsed
            height = geometry.height()
            if self.video_label.isHidden() and self._expanded_height:
                height = self._expanded_height
            self.config_manager.set_window_position(
                'player',
                geometry.x(), geometry.y(),
                geometry.width(), height,
                auto_save=True
            )

        # Pause rather than stop, so restoring the window can resume. The
        # window is only hidden, not destroyed (see restore actions)
        if self.is_playing and not self.is_paused:
            self.play_pause()

        # libVLC's video output dies while the window is hidden; rebuild it on restore
        self._rebuild_vout_on_show = True
        event.accept()

    def release_vlc(self):
        """Stop playback and free all libVLC objects. Called once at app quit.

        Each step is logged so a hang at exit shows which call never returned.
        """
        self.slider_timer.stop()
        self._stop_playback()   # stops and detaches events first

        for name in ('vlc_media', 'vlc_player', 'vlc_instance'):
            obj = getattr(self, name)
            if obj is None:
                continue
            # Clear first so nothing (queued signals, timers) can use it after
            setattr(self, name, None)
            try:
                self.logger.debug(f'exit: releasing {name}')
                obj.release()
                self.logger.debug(f'exit: {name} released')
            except Exception as e:
                self.logger.warning(f'Could not release {name}: {e}')

        self.logger.info('VLC released')

    def showEvent(self, event):
        """Resume slider updates when the window is (re)shown"""
        super().showEvent(event)
        if not self.slider_timer.isActive():
            self.slider_timer.start(100)
        if getattr(self, '_rebuild_vout_on_show', False):
            self._rebuild_vout_on_show = False
            # Wait until the native window is actually visible again
            QTimer.singleShot(0, self._rebuild_video_output)

    def _rebuild_video_output(self):
        """Reattach video after the window was closed and restored.

        Without this only the audio keeps playing: the Direct3D video output
        was torn down while the window was hidden, and libVLC doesn't recreate
        it on its own. Rebinding the window handle and toggling the video
        track forces a fresh video output.
        """
        if not self.vlc_player or self.vlc_media is None:
            return
        try:
            hwnd = int(self.video_label.winId())
            if platform.system() == "Windows":
                self.vlc_player.set_hwnd(hwnd)
            elif platform.system() == "Darwin":
                self.vlc_player.set_nsobject(hwnd)
            else:
                self.vlc_player.set_xwindow(hwnd)

            track = self.vlc_player.video_get_track()
            if track is None or track < 0:
                # No video track selected (audio-only file, or not started)
                return
            self.vlc_player.video_set_track(-1)
            self.vlc_player.video_set_track(track)
            self._seek_on_resume = True
            self.logger.info(f'Rebuilt video output (track {track})')
        except Exception as e:
            self.logger.warning(f'Could not rebuild video output: {e}')

    def hideEvent(self, event):
        """No need to update the slider while the window is hidden"""
        super().hideEvent(event)
        self.slider_timer.stop()

    def bring_to_front(self):
        """Show (or reopen) this window and focus it"""
        self.show()
        self.raise_()
        self.activateWindow()

    def _update_restore_action(self):
        """Only offer 'Restore Playlist Window' when it's actually closed"""
        file_window = app_registry.get('file_window')
        self.restore_playlist_action.setEnabled(
            file_window is not None and not file_window.isVisible())

    def _restore_playlist_window(self):
        file_window = app_registry.get('file_window')
        if file_window:
            file_window.bring_to_front()
