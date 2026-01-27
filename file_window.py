"""
File Window - Contains current playlist and playlist manager panels
"""
from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QAction,
                             QFileDialog, QSplitter)
from PyQt5.QtCore import Qt
import logging

from current_playlist_panel import CurrentPlaylistPanel
from playlist_manager_panel import PlaylistManagerPanel


class FileWindow(QMainWindow):
    """File window for managing playlists and viewing current playlist"""

    def __init__(self, player_window=None, config_manager=None):
        super().__init__()

        self.logger = logging.getLogger(__name__)
        self.logger.debug('Initializing FileWindow')

        self.player_window = player_window
        self.config_manager = config_manager

        self.setWindowTitle("Playlist Manager")
        self.setGeometry(920, 100, 600, 800)

        self._setup_ui()

        self.logger.debug('FileWindow initialized')

    def _setup_ui(self):
        """Setup the user interface"""
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # Splitter for two columns
        splitter = QSplitter(Qt.Horizontal)

        # Left column: Current Playlist
        self.current_playlist_panel = CurrentPlaylistPanel(
            parent=self,
            play_callback=self._on_play_file,
            config_manager=self.config_manager
        )
        splitter.addWidget(self.current_playlist_panel)

        # Right column: Playlist Manager
        self.playlist_manager_panel = PlaylistManagerPanel(parent=self,
                                                           config_manager=self.config_manager)
        splitter.addWidget(self.playlist_manager_panel)

        # Set initial sizes (60% for current playlist, 40% for manager)
        splitter.setSizes([360, 240])

        main_layout.addWidget(splitter)

        # Create menu bar (after panels are created)
        self._create_menus()

    def _create_menus(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu('File')

        load_folder_action = QAction('Load Folder...', self)
        load_folder_action.triggered.connect(self.current_playlist_panel._load_folder)
        file_menu.addAction(load_folder_action)

        load_m3u_action = QAction('Load M3U Playlist...', self)
        load_m3u_action.triggered.connect(self.current_playlist_panel._load_m3u)
        file_menu.addAction(load_m3u_action)

        file_menu.addSeparator()

        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Playlist menu
        playlist_menu = menubar.addMenu('Playlists')

        select_dir_action = QAction('Select Playlist Directory...', self)
        select_dir_action.triggered.connect(
            self.playlist_manager_panel._select_playlist_directory
        )
        playlist_menu.addAction(select_dir_action)

        new_playlist_action = QAction('Create New Playlist...', self)
        new_playlist_action.triggered.connect(
            self.playlist_manager_panel._create_new_playlist
        )
        playlist_menu.addAction(new_playlist_action)

    def _on_play_file(self, file_path):
        """Called when a file should be played"""
        self.logger.info(f'Play request for: {file_path}')

        # Update playlist manager to show current track
        self.playlist_manager_panel.set_current_track(file_path)

        # Tell player window to play the file
        if self.player_window:
            self.player_window.play_file(file_path)

    def handle_player_event(self, event_type, data):
        """Handle events from the player window"""
        if event_type == 'next':
            # Player wants next track
            next_file = self.current_playlist_panel.next_track()
            if next_file and self.player_window:
                self.player_window.play_file(next_file)

        elif event_type == 'previous':
            # Player wants previous track
            prev_file = self.current_playlist_panel.previous_track()
            if prev_file and self.player_window:
                self.player_window.play_file(prev_file)

        elif event_type == 'shuffle':
            # Player toggled shuffle mode
            self.current_playlist_panel.set_shuffle_mode(data)

        elif event_type == 'file_changed':
            # Player changed file (update current file in playlist)
            self.current_playlist_panel.set_current_file(data)
            self.playlist_manager_panel.set_current_track(data)

    def closeEvent(self, event):
        """Handle window close"""
        self.logger.info('Closing file window')

        # Save window position
        if self.config_manager:
            geometry = self.geometry()
            self.config_manager.set_window_position(
                'file',
                geometry.x(), geometry.y(),
                geometry.width(), geometry.height(),
                auto_save=True
            )

        event.accept()

