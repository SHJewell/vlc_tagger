"""
VLC Tagger - New UI Version
Main application that launches both player and file windows

TODO:
    File organization
    Dark mode support
    Make screen collapsible
        Make that default for audio files?
        Audio visualization?
    Audio mixer?
    Small error popup when a file fails to play (see PlayerWindow._handle_media_error)
    Add right-click "remove playlist" option
    Add file info columns: artist, album, etc
        Show file path in tooltip/hovertext
    Add "save as" config to set location.
"""
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import QApplication

from player_window import PlayerWindow
from file_window import FileWindow
from config_manager import ConfigManager

# Components (including this app) are looked up via app_registry.get(...)
import app_registry
import instance
import theme


def setup_logging():
    """Setup application logging"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # One log per instance: two processes rotating the same file
            # fails on Windows and interleaves their lines
            RotatingFileHandler(instance.log_filename(), maxBytes=5_000_000,
                                backupCount=3, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

    # Third-party libraries pulled in transitively (seen in past logs: numba's
    # JIT tracing, which this app never imports directly) log at DEBUG under
    # the root logger and can drown out the player/libvlc lines that actually
    # matter when diagnosing a freeze. Keep them quiet.
    for noisy_logger in ('numba', 'PIL'):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    setup_crash_logging()


_crash_file = None   # kept open for the life of the process, for faulthandler


def setup_crash_logging():
    """Make crashes leave evidence.

    - Python errors inside Qt slots normally make PyQt5 abort the whole app
      with no trace; with an excepthook set they are logged and the app keeps
      running.
    - Hard crashes in native code (VLC, Qt) dump every thread's Python stack
      to vlc_tagger[_N]_crash.log next to the normal log.
    """
    global _crash_file
    import faulthandler

    def log_uncaught(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logging.getLogger('crash').critical('Uncaught exception',
                                            exc_info=(exc_type, exc, tb))

    sys.excepthook = log_uncaught

    crash_log = os.path.splitext(instance.log_filename())[0] + '_crash.log'
    try:
        _crash_file = open(crash_log, 'a', encoding='utf-8')
        _crash_file.write(f'\n--- started pid {os.getpid()} ---\n')
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except OSError as e:
        logging.getLogger(__name__).warning(f'Crash log unavailable: {e}')


class VLCTaggerApp:
    """Main application class"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info(f'Starting VLC Tagger application (instance #{instance.number()})')

        # Initialize config manager
        self.config_manager = ConfigManager()

        # Theme before any window exists, so nothing flashes light first
        theme.apply(self.config_manager.get_dark_mode())

        # Create file window first
        self.file_window = FileWindow(config_manager=self.config_manager)

        # Create player window with callback to file window
        self.player_window = PlayerWindow(
            file_window_callback=self.file_window.handle_player_event,
            config_manager=self.config_manager
        )

        app_registry.register('app', self)
        app_registry.register('config_manager', self.config_manager)
        app_registry.register('file_window', self.file_window)
        app_registry.register('player_window', self.player_window)
        app_registry.register('current_playlist_panel', self.file_window.current_playlist_panel)
        app_registry.register('playlist_manager_panel', self.file_window.playlist_manager_panel)

        # Link windows together
        self.file_window.player_window = self.player_window
        self.player_window.play_state_changed.connect(self.file_window.set_play_state)

        # Closing the player window only pauses; stop and release VLC when
        # the app actually quits
        QApplication.instance().aboutToQuit.connect(self.player_window.release_vlc)

        # Restore window positions from config
        self._restore_window_positions()

        # Show both windows
        self.player_window.show()
        self.file_window.show()

        # Restore previous state
        self._restore_previous_state()

        self.logger.info('Application windows created and displayed')

    def _restore_window_positions(self):
        """Restore window positions from config"""
        # Player window
        player_pos = self.config_manager.get_window_position('player')
        if player_pos:
            self.player_window.setGeometry(
                player_pos['x'], player_pos['y'],
                player_pos['width'], player_pos['height']
            )

        # File window
        file_pos = self.config_manager.get_window_position('file')
        if file_pos:
            self.file_window.setGeometry(
                file_pos['x'], file_pos['y'],
                file_pos['width'], file_pos['height']
            )

    def _restore_previous_state(self):
        """Restore previous playback state from config"""
        # Restore playlist
        playlist_path = self.config_manager.get_current_playlist_path()
        index = self.config_manager.get_current_playlist_index()
        folder = self.config_manager.get_current_folder()

        if playlist_path and os.path.exists(playlist_path):
            # Restore saved playlist
            self.file_window.current_playlist_panel.restore_playlist(
                playlist_path, index, None
            )
        elif folder and os.path.exists(folder):
            # Restore folder view
            self.file_window.current_playlist_panel.restore_playlist(
                None, index, folder
            )

        current_file = self.config_manager.get_current_file()
        # last_position = self.config_manager.get_last_position()   # unused for now

        if current_file and os.path.exists(current_file):
            self.logger.info(f'Restoring previous file: {current_file}')

            # Load the file
            autoplay = self.player_window.autoplay_on_launch
            self.player_window.play_file(current_file, autoplay=autoplay)

    def apply_profile(self):
        """Re-apply the active config profile to every window and panel.

        Called after a profile switch. Saves are suppressed while applying so
        the transient UI churn can't overwrite the freshly loaded profile.
        """
        self.logger.info(f'Applying profile: {self.config_manager.profile_name}')

        with self.config_manager.applying():
            # Player settings first (also stops playback)
            self.player_window.reload_from_config()

            # Playlist manager (playlist directory)
            self.file_window.playlist_manager_panel._load_from_config()

            # Current playlist's columns and sort
            self.file_window.current_playlist_panel.apply_view_settings()

            # Window geometry, then playlist/current file (may start playback
            # depending on the profile's autoplay setting)
            self._restore_window_positions()
            self._restore_previous_state()

    def set_dark_mode(self, enabled: bool):
        """View > Dark Mode from either window: apply, save, sync both menus"""
        theme.apply(enabled)
        self.config_manager.set_dark_mode(enabled)

        self.player_window.dark_mode_action.setChecked(enabled)
        self.file_window.dark_mode_action.setChecked(enabled)

        # Row highlight colors depend on the theme
        self.file_window.playlist_manager_panel._update_highlighting()

    def run(self):
        """Run the application"""
        return app.exec_()


if __name__ == "__main__":
    # Before logging: the instance number picks the log file
    instance.claim()
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("VLC Tagger")
    app.setOrganizationName("VLC Tagger")

    vlc_app = VLCTaggerApp()

    sys.exit(vlc_app.run())
