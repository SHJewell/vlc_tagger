from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QListWidget,
                             QLabel, QFileDialog, QListWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import os
import logging

class PlaylistPanel(QWidget):
    def __init__(self, parent, callback_play):
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)
        self.logger.debug('Initializing PlaylistPanel')

        self.callback_play = callback_play
        self.playlist_files = []
        self.current_index = -1

        # Create main layout
        layout = QVBoxLayout(self)

        # Title label
        title_label = QLabel("Folder Playlist")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Create a button to select folder
        self.folder_button = QPushButton("Select Folder")
        self.folder_button.clicked.connect(self.select_folder)
        layout.addWidget(self.folder_button)

        # Create a listbox to display files
        self.playlist_box = QListWidget()
        self.playlist_box.itemDoubleClicked.connect(self.play_selected)
        layout.addWidget(self.playlist_box)

        self.logger.debug('PlaylistPanel initialized')

    def select_folder(self):
        """Open folder dialog and load video files into playlist"""
        self.logger.debug('Selecting folder for playlist')
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self.logger.info(f'Folder selected: {folder_path}')
            self.load_playlist(folder_path)
        else:
            self.logger.info('No folder selected')

    def load_playlist(self, folder_path):
        """Load all video files from the selected folder"""
        self.logger.debug(f'Loading playlist from {folder_path}')

        # Clear current playlist
        self.playlist_box.clear()
        self.playlist_files = []

        # Video file extensions to look for
        video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv')

        try:
            # Get all files in the folder
            files = os.listdir(folder_path)

            # Filter for video files and add them to the playlist
            for file in files:
                if file.lower().endswith(video_extensions):
                    full_path = os.path.join(folder_path, file)
                    self.playlist_files.append(full_path)
                    self.playlist_box.addItem(file)  # Show just the filename

            self.logger.info(f'Loaded {len(self.playlist_files)} video files')
        except Exception as e:
            self.logger.error(f'Error loading playlist: {e}')

    def add_to_playlist(self, file_path):
        """Add a single file to the playlist"""
        if file_path not in self.playlist_files:
            self.playlist_files.append(file_path)
            filename = os.path.basename(file_path)
            self.playlist_box.addItem(filename)
            self.logger.debug(f'Added {filename} to playlist')

            # If this is the first file, set it as current
            if len(self.playlist_files) == 1:
                self.current_index = 0
                self.playlist_box.setCurrentRow(0)
        else:
            # If the file is already in the playlist, select it only if this panel is being used
            index = self.playlist_files.index(file_path)
            self.current_index = index
            self.playlist_box.setCurrentRow(index)
            self.logger.debug(f'File already in playlist, selected at index {index}')

    def set_current_file(self, file_path):
        """Set current file without affecting UI selection - for internal tracking only"""
        if file_path in self.playlist_files:
            self.current_index = self.playlist_files.index(file_path)
            self.logger.debug(f'Updated current index to {self.current_index} for file: {file_path}')
            return True
        return False

    def update_visual_selection(self, file_path):
        """Update the visual selection in this panel"""
        if file_path in self.playlist_files:
            index = self.playlist_files.index(file_path)
            self.current_index = index
            self.playlist_box.setCurrentRow(index)
            self.logger.debug(f'Updated visual selection to index {index}')

    def clear_visual_selection(self):
        """Clear the visual selection in this panel"""
        self.playlist_box.clearSelection()
        self.playlist_box.setCurrentRow(-1)

    def play_selected(self, item=None):
        """Play the selected file in the playlist"""
        current_row = self.playlist_box.currentRow()
        if current_row >= 0:
            self.current_index = current_row
            self.logger.debug(f'Selected file at index {current_row}: {self.playlist_files[current_row]}')
            self.callback_play(self.playlist_files[current_row])
            # Highlight the currently playing item
            self.playlist_box.setCurrentRow(current_row)

    def next_track(self):
        """Play the next track in the playlist"""
        if not self.playlist_files:
            self.logger.debug('No tracks in playlist')
            return None

        if self.current_index < len(self.playlist_files) - 1:
            self.current_index += 1
            self.playlist_box.setCurrentRow(self.current_index)
            self.logger.info(f'Moving to next track: {self.playlist_files[self.current_index]}')
            return self.playlist_files[self.current_index]
        else:
            self.logger.info('Already at last track')
            return None

    def previous_track(self):
        """Play the previous track in the playlist"""
        if not self.playlist_files:
            self.logger.debug('No tracks in playlist')
            return None

        if self.current_index > 0:
            self.current_index -= 1
            self.playlist_box.setCurrentRow(self.current_index)
            self.logger.info(f'Moving to previous track: {self.playlist_files[self.current_index]}')
            return self.playlist_files[self.current_index]
        else:
            self.logger.info('Already at first track')
            return None
