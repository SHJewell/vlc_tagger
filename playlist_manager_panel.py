"""
Playlist Manager Panel - Shows available playlists and allows adding/removing current track
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QListWidget, QMenu,
                             QLabel, QFileDialog, QListWidgetItem, QMessageBox, QInputDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
import os
import logging
from pathlib import Path

# local imports
import app_registry

class PlaylistManagerPanel(QWidget):
    """Panel for managing multiple M3U playlists"""

    def __init__(self, parent=None, config_manager=None):
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)
        self.config_manager = config_manager
        self.playlists = {}
        self.playlist_dir = None
        self.current_track = None

        self._setup_ui()
        self._load_from_config()

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)

        title_label = QLabel("Playlist Manager")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        self.select_dir_button = QPushButton("📁 Select Playlist Directory")
        self.select_dir_button.clicked.connect(self._select_playlist_directory)
        layout.addWidget(self.select_dir_button)

        self.dir_label = QLabel("No directory selected")
        self.dir_label.setWordWrap(True)
        self.dir_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(self.dir_label)

        self.playlist_list = QListWidget()
        self.playlist_list.itemClicked.connect(self._on_playlist_clicked)
        self.playlist_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.playlist_list)

        self.new_playlist_button = QPushButton("➕ Create New Playlist")
        self.new_playlist_button.clicked.connect(self._create_new_playlist)
        self.new_playlist_button.setEnabled(False)
        layout.addWidget(self.new_playlist_button)

    def _load_from_config(self):
        """Load playlist directory from config if available"""
        if not self.config_manager:
            return

        saved_dir = self.config_manager.get_playlist_directory()
        if saved_dir and os.path.isdir(saved_dir):
            self.playlist_dir = saved_dir
            self.dir_label.setText(f"Directory: {os.path.basename(saved_dir)}")
            self.dir_label.setToolTip(f"<b>{saved_dir}</b>")
            self.new_playlist_button.setEnabled(True)
            self._load_playlists()
        else:
            # No (valid) directory in this profile — reset the panel so a
            # profile switch doesn't leave the previous profile's playlists
            self.playlist_dir = None
            self.playlists.clear()
            self.playlist_list.clear()
            self.dir_label.setText("No directory selected")
            self.dir_label.setToolTip("")
            self.new_playlist_button.setEnabled(False)

    def _select_playlist_directory(self):
        """Open dialog to select directory containing playlists"""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Playlist Directory")

        if dir_path:
            self.playlist_dir = dir_path
            self.dir_label.setText(f"Directory: {os.path.basename(dir_path)}")
            self.dir_label.setToolTip(f"<b>{dir_path}</b>")
            self.new_playlist_button.setEnabled(True)

            # Save to config
            if self.config_manager:
                self.config_manager.set_playlist_directory(dir_path, auto_save=True)

            self._load_playlists()

    def _load_playlists(self):
        """Load all M3U/M3U8 playlists from the selected directory"""
        if not self.playlist_dir:
            return

        self.playlists.clear()
        self.playlist_list.clear()

        try:
            for filename in os.listdir(self.playlist_dir):
                if filename.lower().endswith(('.m3u', '.m3u8')):
                    playlist_path = os.path.join(self.playlist_dir, filename)
                    files = self._parse_m3u_file(playlist_path)
                    self.playlists[playlist_path] = files

                    item = QListWidgetItem(os.path.splitext(filename)[0])
                    item.setData(Qt.UserRole, playlist_path)
                    self.playlist_list.addItem(item)

            if self.current_track:
                self._update_highlighting()

        except Exception as e:
            self.logger.error(f'Error loading playlists: {e}')

    def _parse_m3u_file(self, file_path):
        """Parse M3U file and return list of file paths"""
        files = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            playlist_dir = os.path.dirname(file_path)

            for line in lines:
                line = line.strip()

                if not line or line.startswith('#'):
                    continue

                file_url = line

                if not (file_url.startswith('http') or file_url.startswith('https')):
                    if not os.path.isabs(file_url):
                        file_url = os.path.join(playlist_dir, file_url)
                    file_url = os.path.normcase(os.path.normpath(file_url))

                files.append(file_url)

        except Exception as e:
            self.logger.error(f'Error parsing M3U file {file_path}: {e}')

        return files

    def _show_context_menu(self, position):
        """Show context menu for playlist items"""
        item = self.playlist_list.itemAt(position)

        if not item:
            return

        menu = QMenu(self)
        load_action = menu.addAction("Load Playlist")

        action = menu.exec_(self.playlist_list.mapToGlobal(position))

        if action == load_action:
            self._load_playlist_as_current(item)

    def _load_playlist_as_current(self, item):
        """Load the selected playlist into the main player"""
        playlist_path = item.data(Qt.UserRole)
        playlist_path = Path(playlist_path).resolve()

        self.logger.info(f'Switching playlist {playlist_path} into main player')
        current_playlist_panel = app_registry.get("current_playlist_panel")

        try:
            current_playlist_panel._load_m3u(playlist_path)
        except Exception as e:
            self.logger.error(f'Could not find CurrentPlaylistPanel instance to load {playlist_path}')
            self.logger.error(f'Error loading playlist into main player: {e}')

    def _save_m3u_file(self, playlist_path, files):
        """Save playlist to M3U file"""
        try:
            self.logger.debug(f'Saving playlist to {playlist_path}')

            with open(playlist_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")

                for file_path in files:
                    filename = os.path.basename(file_path)
                    f.write(f"#EXTINF:-1,{filename}\n")

                    f.write(f"{file_path}\n")

            return True

        except Exception as e:
            self.logger.error(f'Error saving M3U file {playlist_path}: {e}')
            return False

    def _on_playlist_clicked(self, item):
        """Handle playlist item click - add or remove current track"""
        if not self.current_track:
            QMessageBox.information(self, "No Track Playing",
                                   "Please play a track first before managing playlists.")
            return

        playlist_path = item.data(Qt.UserRole)
        files = self.playlists.get(playlist_path, [])

        normalized_track = os.path.normcase(os.path.normpath(self.current_track))

        if normalized_track in files:
            files.remove(normalized_track)
            self.playlists[playlist_path] = files
            self._save_m3u_file(playlist_path, files)
        else:
            files.append(normalized_track)
            self.playlists[playlist_path] = files
            self._save_m3u_file(playlist_path, files)

        # Add to recent playlists
        if self.config_manager:
            self.config_manager.add_recent_playlist(playlist_path, auto_save=True)

        self._update_highlighting()

    def _create_new_playlist(self):
        """Create a new empty playlist"""
        if not self.playlist_dir:
            return

        name, ok = QInputDialog.getText(self, "New Playlist", "Enter playlist name:")

        if ok and name:
            filename = f"{name}.m3u"
            playlist_path = os.path.join(self.playlist_dir, filename)

            if os.path.exists(playlist_path):
                QMessageBox.warning(self, "Playlist Exists",
                                   f"A playlist named '{name}' already exists.")
                return

            self.playlists[playlist_path] = []
            self._save_m3u_file(playlist_path, [])

            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, playlist_path)
            self.playlist_list.addItem(item)

    def set_current_track(self, file_path):
        """Update the current track and highlight playlists containing it"""
        self.current_track = os.path.normcase(os.path.normpath(file_path)) if file_path else None
        self._update_highlighting()

    def _update_highlighting(self):
        """Highlight playlists that contain the current track"""
        if not self.current_track:
            return

        for i in range(self.playlist_list.count()):
            item = self.playlist_list.item(i)
            playlist_path = item.data(Qt.UserRole)
            files = self.playlists.get(playlist_path, [])

            if self.current_track in files:
                item.setBackground(QColor(173, 216, 230))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            else:
                item.setBackground(QColor(255, 255, 255))
                font = item.font()
                font.setBold(False)
                item.setFont(font)
