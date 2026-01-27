"""
Current Playlist Panel - Shows the current playlist or directory being played
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QListWidget,
                             QLabel, QFileDialog, QListWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import os
import logging
import random


class CurrentPlaylistPanel(QWidget):
    """Panel showing current playlist/directory being played"""

    def __init__(self, parent=None, play_callback=None, config_manager=None):
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)
        self.play_callback = play_callback
        self.config_manager = config_manager

        self.playlist_files = []
        self.current_index = -1
        self.shuffle_mode = False
        self.shuffle_history = []
        self.current_folder = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Current Playlist")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Load buttons
        button_layout = QVBoxLayout()

        self.load_folder_button = QPushButton("📁 Load Folder")
        self.load_folder_button.clicked.connect(self._load_folder)
        button_layout.addWidget(self.load_folder_button)

        self.load_m3u_button = QPushButton("📄 Load M3U Playlist")
        self.load_m3u_button.clicked.connect(self._load_m3u)
        button_layout.addWidget(self.load_m3u_button)

        layout.addLayout(button_layout)

        # Playlist name
        self.playlist_name_label = QLabel("No playlist loaded")
        self.playlist_name_label.setWordWrap(True)
        self.playlist_name_label.setStyleSheet("font-style: italic; color: gray;")
        layout.addWidget(self.playlist_name_label)

        # File list
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        layout.addWidget(self.file_list)

        # Clear button
        self.clear_button = QPushButton("Clear Playlist")
        self.clear_button.clicked.connect(self._clear_playlist)
        layout.addWidget(self.clear_button)

    def _load_folder(self):
        """Load all media files from a selected folder"""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Media Folder")

        if folder_path:
            self.logger.info(f'Loading folder: {folder_path}')
            self._clear_playlist()

            self.current_folder = folder_path

            # Media file extensions
            media_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
                              '.mp3', '.wav', '.flac', '.ogg', '.m4a')

            try:
                files = os.listdir(folder_path)

                for file in sorted(files):
                    if file.lower().endswith(media_extensions):
                        full_path = os.path.join(folder_path, file)
                        self.playlist_files.append(full_path)
                        self.file_list.addItem(file)

                self.playlist_name_label.setText(f"Folder: {os.path.basename(folder_path)}")
                self.logger.info(f'Loaded {len(self.playlist_files)} files from folder')

                # Save to config
                if self.config_manager:
                    self.config_manager.update_playlist_state(
                        playlist=self.playlist_files,
                        index=0 if self.playlist_files else -1,
                        folder=folder_path,
                        auto_save=True
                    )

                # Auto-play first file
                if self.playlist_files:
                    self.current_index = 0
                    self.file_list.setCurrentRow(0)
                    if self.play_callback:
                        self.play_callback(self.playlist_files[0])

            except Exception as e:
                self.logger.error(f'Error loading folder: {e}')

    def _load_m3u(self):
        """Load M3U/M3U8 playlist file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select M3U Playlist",
            "",
            "M3U files (*.m3u *.m3u8);;All files (*.*)"
        )

        if file_path:
            self.logger.info(f'Loading M3U: {file_path}')
            self._clear_playlist()

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                playlist_dir = os.path.dirname(file_path)
                current_title = None

                for line in lines:
                    line = line.strip()

                    if not line:
                        continue

                    if line.startswith('#EXTINF:'):
                        if ',' in line:
                            current_title = line.split(',', 1)[1].strip()
                    elif line.startswith('#'):
                        continue
                    else:
                        file_url = line
                        display_name = current_title if current_title else os.path.basename(file_url)

                        # Handle relative paths
                        if not (file_url.startswith('http') or file_url.startswith('https') or os.path.isabs(file_url)):
                            file_url = os.path.join(playlist_dir, file_url)
                            file_url = os.path.normpath(file_url)

                        self.playlist_files.append(file_url)
                        self.file_list.addItem(display_name)
                        current_title = None

                self.playlist_name_label.setText(f"Playlist: {os.path.basename(file_path)}")
                self.logger.info(f'Loaded {len(self.playlist_files)} files from M3U')

                # Save to config
                if self.config_manager:
                    self.config_manager.update_playlist_state(
                        playlist=self.playlist_files,
                        index=0 if self.playlist_files else -1,
                        folder=playlist_dir,
                        auto_save=True
                    )
                    self.config_manager.add_recent_playlist(file_path, auto_save=True)

                # Auto-play first file
                if self.playlist_files:
                    self.current_index = 0
                    self.file_list.setCurrentRow(0)
                    if self.play_callback:
                        self.play_callback(self.playlist_files[0])

            except Exception as e:
                self.logger.error(f'Error loading M3U: {e}')

    def _clear_playlist(self):
        """Clear the current playlist"""
        self.playlist_files.clear()
        self.file_list.clear()
        self.current_index = -1
        self.shuffle_history.clear()
        self.current_folder = None
        self.playlist_name_label.setText("No playlist loaded")

        # Save cleared state to config
        if self.config_manager:
            self.config_manager.update_playlist_state(
                playlist=[],
                index=-1,
                folder=None,
                auto_save=True
            )

    def _on_file_double_clicked(self, item):
        """Handle double-click on a file"""
        row = self.file_list.row(item)
        if 0 <= row < len(self.playlist_files):
            self.current_index = row
            if self.play_callback:
                self.play_callback(self.playlist_files[row])

    def set_current_file(self, file_path):
        """Set the current file and update selection"""
        if file_path in self.playlist_files:
            self.current_index = self.playlist_files.index(file_path)
            self.file_list.setCurrentRow(self.current_index)

            # Save current index to config
            if self.config_manager:
                self.config_manager.set_current_playlist_index(self.current_index, auto_save=True)

            self.logger.debug(f'Current file set to index {self.current_index}')

    def next_track(self):
        """Get the next track in the playlist"""
        if not self.playlist_files:
            return None

        if self.shuffle_mode:
            # Shuffle mode
            available = [i for i in range(len(self.playlist_files)) if i != self.current_index]
            if not available:
                return None

            next_index = random.choice(available)
            self.shuffle_history.append(self.current_index)
        else:
            # Normal sequential playback
            if self.current_index < len(self.playlist_files) - 1:
                next_index = self.current_index + 1
            else:
                return None  # End of playlist

        self.current_index = next_index
        self.file_list.setCurrentRow(next_index)

        # Save current index to config
        if self.config_manager:
            self.config_manager.set_current_playlist_index(self.current_index, auto_save=True)

        return self.playlist_files[next_index]

    def previous_track(self):
        """Get the previous track in the playlist"""
        if not self.playlist_files:
            return None

        if self.shuffle_mode and self.shuffle_history:
            # Go back in shuffle history
            prev_index = self.shuffle_history.pop()
        else:
            # Normal sequential playback
            if self.current_index > 0:
                prev_index = self.current_index - 1
            else:
                return None  # Start of playlist

        self.current_index = prev_index
        self.file_list.setCurrentRow(prev_index)

        # Save current index to config
        if self.config_manager:
            self.config_manager.set_current_playlist_index(self.current_index, auto_save=True)

        return self.playlist_files[prev_index]

    def set_shuffle_mode(self, enabled):
        """Enable or disable shuffle mode"""
        self.shuffle_mode = enabled
        if not enabled:
            self.shuffle_history.clear()
        self.logger.info(f'Shuffle mode: {enabled}')

    def get_current_file(self):
        """Get the currently selected file"""
        if 0 <= self.current_index < len(self.playlist_files):
            return self.playlist_files[self.current_index]
        return None

    def restore_playlist(self, playlist_files, index, folder):
        """
        Restore playlist state from saved config

        Args:
            playlist_files: List of file paths
            index: Current playlist index
            folder: Current folder path
        """
        self.logger.info(f'Restoring playlist with {len(playlist_files)} files')

        # Clear current playlist first
        self._clear_playlist()

        # Restore files
        self.playlist_files = playlist_files.copy()
        self.current_index = index if 0 <= index < len(playlist_files) else -1
        self.current_folder = folder

        # Populate the file list
        for file_path in playlist_files:
            display_name = os.path.basename(file_path)
            self.file_list.addItem(display_name)

        # Set current selection
        if 0 <= self.current_index < len(playlist_files):
            self.file_list.setCurrentRow(self.current_index)

        # Update label
        if folder:
            self.playlist_name_label.setText(f"Folder: {os.path.basename(folder)}")
        elif playlist_files:
            self.playlist_name_label.setText(f"Playlist: {len(playlist_files)} files")
        else:
            self.playlist_name_label.setText("No playlist loaded")

        self.logger.info(f'Playlist restored with index {self.current_index}')

