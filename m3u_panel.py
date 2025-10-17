from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QListWidget,
                             QLabel, QFileDialog, QListWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import os
import logging

class M3UPanel(QWidget):
    def __init__(self, parent, callback_play):
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)
        self.logger.debug('Initializing M3UPanel')

        self.callback_play = callback_play
        self.playlist_files = []
        self.current_index = -1
        self.playlist_title = ""

        # Create main layout
        layout = QVBoxLayout(self)

        # Title label
        title_label = QLabel("M3U Playlists")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Create a button to select M3U file
        self.file_button = QPushButton("Load M3U/M3U8")
        self.file_button.clicked.connect(self.load_m3u_file)
        layout.addWidget(self.file_button)

        # Playlist name display
        self.playlist_name_label = QLabel("No playlist loaded")
        self.playlist_name_label.setWordWrap(True)
        layout.addWidget(self.playlist_name_label)

        # Create a listbox to display playlist items
        self.playlist_box = QListWidget()
        self.playlist_box.itemDoubleClicked.connect(self.play_selected)
        layout.addWidget(self.playlist_box)

        self.logger.debug('M3UPanel initialized')

    def load_m3u_file(self):
        """Open file dialog and load M3U/M3U8 playlist"""
        self.logger.debug('Selecting M3U playlist file')
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select M3U Playlist",
            "",
            "M3U files (*.m3u);;M3U8 files (*.m3u8);;All files (*.*)"
        )
        if file_path:
            self.logger.info(f'M3U file selected: {file_path}')
            self.parse_m3u_file(file_path)
        else:
            self.logger.info('No M3U file selected')

    def parse_m3u_file(self, file_path):
        """Parse M3U/M3U8 playlist file"""
        self.logger.debug(f'Parsing M3U file: {file_path}')

        # Clear current playlist
        self.playlist_box.clear()
        self.playlist_files = []
        self.playlist_title = ""

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            playlist_dir = os.path.dirname(file_path)
            current_title = None

            for line in lines:
                line = line.strip()

                # Skip empty lines and comments (except #EXTINF)
                if not line:
                    continue

                # Handle playlist title
                if line.startswith('#PLAYLIST:'):
                    self.playlist_title = line[10:].strip()

                # Handle track info
                elif line.startswith('#EXTINF:'):
                    # Extract title from EXTINF line
                    if ',' in line:
                        current_title = line.split(',', 1)[1].strip()

                # Skip other comments
                elif line.startswith('#'):
                    continue

                # This should be a file path or URL
                else:
                    file_url = line
                    display_name = current_title if current_title else os.path.basename(file_url)

                    # Handle relative paths
                    if not (file_url.startswith('http') or file_url.startswith('https') or os.path.isabs(file_url)):
                        file_url = os.path.join(playlist_dir, file_url)
                        file_url = os.path.normpath(file_url)

                    # Add to playlist
                    self.playlist_files.append(file_url)
                    self.playlist_box.addItem(display_name)

                    # Reset current title for next track
                    current_title = None

            # Update playlist name display
            display_name = self.playlist_title if self.playlist_title else os.path.basename(file_path)
            self.playlist_name_label.setText(display_name)

            self.logger.info(f'Loaded {len(self.playlist_files)} items from M3U playlist')

        except Exception as e:
            self.logger.error(f'Error parsing M3U file: {e}')
            self.playlist_name_label.setText("Error loading playlist")

    def add_to_playlist(self, file_path):
        """Add a single file to the playlist (for compatibility)"""
        if file_path not in self.playlist_files:
            self.playlist_files.append(file_path)
            filename = os.path.basename(file_path)
            self.playlist_box.addItem(filename)
            self.logger.debug(f'Added {filename} to M3U playlist')

            # If this is the first file, set it as current
            if len(self.playlist_files) == 1:
                self.current_index = 0
                self.playlist_box.setCurrentRow(0)
        else:
            # If the file is already in the playlist, select it only if this panel is being used
            index = self.playlist_files.index(file_path)
            self.current_index = index
            self.playlist_box.setCurrentRow(index)
            self.logger.debug(f'File already in M3U playlist, selected at index {index}')

    def set_current_file(self, file_path):
        """Set current file without affecting UI selection - for internal tracking only"""
        if file_path in self.playlist_files:
            self.current_index = self.playlist_files.index(file_path)
            self.logger.debug(f'Updated current index to {self.current_index} for M3U file: {file_path}')
            return True
        return False

    def update_visual_selection(self, file_path):
        """Update the visual selection in this panel"""
        if file_path in self.playlist_files:
            index = self.playlist_files.index(file_path)
            self.current_index = index
            self.playlist_box.setCurrentRow(index)
            self.logger.debug(f'Updated M3U visual selection to index {index}')

    def clear_visual_selection(self):
        """Clear the visual selection in this panel"""
        self.playlist_box.clearSelection()
        self.playlist_box.setCurrentRow(-1)

    def play_selected(self, item=None):
        """Play the selected file in the playlist"""
        current_row = self.playlist_box.currentRow()
        if current_row >= 0:
            self.current_index = current_row
            self.logger.debug(f'Selected M3U item at index {current_row}: {self.playlist_files[current_row]}')
            self.callback_play(self.playlist_files[current_row])
            # Highlight the currently playing item
            self.playlist_box.setCurrentRow(current_row)

    def next_track(self):
        """Play the next track in the playlist"""
        if not self.playlist_files:
            self.logger.debug('No tracks in M3U playlist')
            return None

        if self.current_index < len(self.playlist_files) - 1:
            self.current_index += 1
            self.playlist_box.setCurrentRow(self.current_index)
            self.logger.info(f'Moving to next M3U track: {self.playlist_files[self.current_index]}')
            return self.playlist_files[self.current_index]
        else:
            self.logger.info('Already at last M3U track')
            return None

    def previous_track(self):
        """Play the previous track in the playlist"""
        if not self.playlist_files:
            self.logger.debug('No tracks in M3U playlist')
            return None

        if self.current_index > 0:
            self.current_index -= 1
            self.playlist_box.setCurrentRow(self.current_index)
            self.logger.info(f'Moving to previous M3U track: {self.playlist_files[self.current_index]}')
            return self.playlist_files[self.current_index]
        else:
            self.logger.info('Already at first M3U track')
            return None
