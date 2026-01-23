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
import logging
from PyQt5.QtWidgets import QApplication

from player_window import PlayerWindow
from file_window import FileWindow


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

        # Create file window first
        self.file_window = FileWindow()

        # Create player window with callback to file window
        self.player_window = PlayerWindow(
            file_window_callback=self.file_window.handle_player_event
        )

        # Link windows together
        self.file_window.player_window = self.player_window

        # Show both windows
        self.player_window.show()
        self.file_window.show()

        self.logger.info('Application windows created and displayed')

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
