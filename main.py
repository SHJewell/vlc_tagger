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

from player_window import PlayerWindow
from file_window import FileWindow
from config_manager import ConfigManager


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
        self.logger = logging.getLogger(__name__)
        self.logger.info('Starting VLC Tagger application')

        # Initialize config manager
        self.config_manager = ConfigManager()

        # Create file window first
        self.file_window = FileWindow(config_manager=self.config_manager)

        # Create player window with callback to file window
        self.player_window = PlayerWindow(
            file_window_callback=self.file_window.handle_player_event,
            config_manager=self.config_manager
        )

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

        # Don't auto-play on startup - just restore the state
        # User can press play if they want to resume

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
