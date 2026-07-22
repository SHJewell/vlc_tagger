"""
VLC Tagger - New UI Version
Main application that launches both player and file windows

TODO:
    File organization
    Dark mode support
    Undo button for "Clear Playlist" button
        Or maybe just get rid of it entirely?
    Preferences and configs
    Make screen collapsible
        Make that default for audio files?
        Audio visualization?
    Audio mixer?
"""
import sys
import os
import logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from player_window import PlayerWindow
from file_window import FileWindow
from config_manager import ConfigManager

# Module-level reference to the running app instance
import app_registry
_app_instance = None


def get_app():
    """Get the running VLCTaggerApp instance"""
    return _app_instance

def setup_logging():
    """Setup application logging"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("vlc_tagger.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


class VLCTaggerApp:
    """Main application class"""

    def __init__(self):
        global _app_instance
        _app_instance = self

        self.logger = logging.getLogger(__name__)
        self.logger.info('Starting VLC Tagger application')

        # Central component registry — keyed by component name
        # Only one instance of each is allowed at a time
        self._components: dict = {}

        # Initialize config manager
        self.config_manager = ConfigManager()

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

            # Window geometry, then playlist/current file (may start playback
            # depending on the profile's autoplay setting)
            self._restore_window_positions()
            self._restore_previous_state()

    def run(self):
        """Run the application"""
        return app.exec_()


if __name__ == "__main__":
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("VLC Tagger")
    app.setOrganizationName("VLC Tagger")

    vlc_app = VLCTaggerApp()

    sys.exit(vlc_app.run())
