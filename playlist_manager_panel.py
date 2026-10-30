"""
Playlist Manager Panel - Shows available playlists and allows adding/removing current track
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QMenu,
                             QLabel, QFileDialog, QListWidgetItem, QMessageBox, QInputDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QBrush
import os
import logging
from pathlib import Path

# local imports
import app_registry
import theme
from config_manager import sanitize_filename
from m3u_file import M3UFile, track_key


def _same_path(path):
    """Comparable form of a playlist path (Windows paths ignore case)"""
    return os.path.normcase(os.path.abspath(path))

class PlaylistManagerPanel(QWidget):
    """Panel for managing multiple M3U playlists"""

    def __init__(self, parent=None, config_manager=None):
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)
        self.config_manager = config_manager
        # playlist path -> track keys (normalized, for comparing only)
        self.playlists = {}
        self.playlist_dir = None
        self.current_track = None       # key of the playing track
        self.current_track_path = None  # its path as given, written to playlists

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

        self.dir_label = QLabel("No directory selected")
        self.dir_label.setWordWrap(True)
        self.dir_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(self.dir_label)

        self.playlist_list = QListWidget()
        self.playlist_list.itemClicked.connect(self._on_playlist_clicked)
        self.playlist_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.playlist_list)

    def _load_from_config(self):
        """Load playlist directory from config if available"""
        if not self.config_manager:
            return

        saved_dir = self.config_manager.get_playlist_directory()
        if saved_dir and os.path.isdir(saved_dir):
            self.playlist_dir = saved_dir
            self.dir_label.setText(f"Directory: {os.path.basename(saved_dir)}")
            self.dir_label.setToolTip(f"<b>{saved_dir}</b>")
        else:
            # No (valid) directory in this profile — reset so a profile
            # switch doesn't leave the previous profile's directory
            self.playlist_dir = None
            self.dir_label.setText("No directory selected")
            self.dir_label.setToolTip("")

        # Always reload: the profile may have added playlists even without
        # a directory, and a switch must clear the previous profile's list
        self._load_playlists()

    def _select_playlist_directory(self):
        """Open dialog to select directory containing playlists"""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Playlist Directory")

        if dir_path:
            self.playlist_dir = dir_path
            self.dir_label.setText(f"Directory: {os.path.basename(dir_path)}")
            self.dir_label.setToolTip(f"<b>{dir_path}</b>")

            # Save to config
            if self.config_manager:
                self.config_manager.set_playlist_directory(dir_path, auto_save=True)

            self._load_playlists()

    def _load_playlists(self):
        """List this profile's playlists: those in the playlist directory
        (minus any removed from the profile) plus any added from elsewhere"""
        self.playlists.clear()
        self.playlist_list.clear()

        paths = []
        if self.playlist_dir:
            hidden = {_same_path(p) for p in self._hidden_playlists()}
            try:
                for filename in sorted(os.listdir(self.playlist_dir), key=str.lower):
                    if filename.lower().endswith(('.m3u', '.m3u8')):
                        path = os.path.join(self.playlist_dir, filename)
                        if _same_path(path) not in hidden:
                            paths.append(path)
            except Exception as e:
                self.logger.error(f'Error loading playlists: {e}')

        seen = {_same_path(p) for p in paths}
        for path in self._added_playlists():
            if _same_path(path) in seen:
                continue
            if not os.path.isfile(path):
                self.logger.warning(f'Profile playlist not found, skipping: {path}')
                continue
            seen.add(_same_path(path))
            paths.append(path)

        for path in paths:
            self._add_list_item(path)
            self.playlists[path] = self._parse_m3u_file(path)

        if self.current_track:
            self._update_highlighting()

    def _add_list_item(self, playlist_path):
        item = QListWidgetItem(os.path.splitext(os.path.basename(playlist_path))[0])
        item.setData(Qt.UserRole, playlist_path)
        item.setToolTip(os.path.abspath(playlist_path))
        self.playlist_list.addItem(item)

    def _added_playlists(self):
        return list(self.config_manager.get_default_playlists()) if self.config_manager else []

    def _hidden_playlists(self):
        return list(self.config_manager.get_hidden_playlists()) if self.config_manager else []

    def _in_playlist_dir(self, path):
        return bool(self.playlist_dir) and \
            _same_path(os.path.dirname(path)) == _same_path(self.playlist_dir)

    def _add_playlists_to_profile(self):
        """Pick playlist files (from anywhere) to show in this profile"""
        if not self.config_manager:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Playlists to Profile", self.playlist_dir or "",
            "M3U Playlists (*.m3u *.m3u8)")
        if not paths:
            return
        self._add_paths_to_profile(paths)

    def _add_paths_to_profile(self, paths):
        added, hidden = self._added_playlists(), self._hidden_playlists()
        for path in paths:
            path = os.path.abspath(path)
            key = _same_path(path)
            # Un-hide it if it was removed earlier
            hidden = [p for p in hidden if _same_path(p) != key]
            # Directory playlists show anyway; only track ones from elsewhere
            if not self._in_playlist_dir(path) and \
                    key not in {_same_path(p) for p in added}:
                added.append(path)

        self.config_manager.set_default_playlists(added, auto_save=False)
        self.config_manager.set_hidden_playlists(hidden, auto_save=True)
        self._load_playlists()

    def _remove_playlist_from_profile(self, item):
        """Stop showing a playlist in this profile. The file is not deleted."""
        if not self.config_manager:
            return
        path = item.data(Qt.UserRole)
        key = _same_path(path)

        added = [p for p in self._added_playlists() if _same_path(p) != key]
        hidden = self._hidden_playlists()
        if self._in_playlist_dir(path) and key not in {_same_path(p) for p in hidden}:
            hidden.append(os.path.abspath(path))

        self.config_manager.set_default_playlists(added, auto_save=False)
        self.config_manager.set_hidden_playlists(hidden, auto_save=True)
        self.logger.info(f'Removed {path} from profile (file kept)')
        self._load_playlists()

    def _parse_m3u_file(self, file_path):
        """Parse M3U file and return its track keys (for highlighting)"""
        try:
            return M3UFile.read(file_path).keys()
        except Exception as e:
            self.logger.error(f'Error parsing M3U file {file_path}: {e}')
            return []

    def _show_context_menu(self, position):
        """Show context menu for playlist items"""
        item = self.playlist_list.itemAt(position)

        menu = QMenu(self)
        load_action = remove_action = None

        menu.addAction("Select Playlist Directory...",
                       self._select_playlist_directory)
        new_action = menu.addAction("Create New Playlist...",
                                    self._create_new_playlist)
        new_action.setEnabled(bool(self.playlist_dir))

        menu.addSeparator()

        if item:
            load_action = menu.addAction("Load As Current Playlist")
            menu.addSeparator()
            remove_action = menu.addAction("Remove from Profile")
            remove_action.setEnabled(self.config_manager is not None)

        add_action = menu.addAction("Add Playlists to Profile...",
                                    self._add_playlists_to_profile)
        add_action.setEnabled(self.config_manager is not None)


        action = menu.exec_(self.playlist_list.mapToGlobal(position))

        if item and action == load_action:
            self._load_playlist_as_current(item)
        elif item and action == remove_action:
            self._remove_playlist_from_profile(item)

    def _load_playlist_as_current(self, item):
        """Load the selected playlist into the main player"""
        playlist_path = item.data(Qt.UserRole)
        # Keep it a str: a Path stored in config breaks restore_playlist's .lower()
        playlist_path = str(Path(playlist_path).resolve())

        self.logger.info(f'Switching playlist {playlist_path} into main player')
        current_playlist_panel = app_registry.get("current_playlist_panel")

        try:
            current_playlist_panel._load_m3u(playlist_path)
        except Exception as e:
            self.logger.error(f'Could not find CurrentPlaylistPanel instance to load {playlist_path}')
            self.logger.error(f'Error loading playlist into main player: {e}')

    def _on_playlist_clicked(self, item):
        """Handle playlist item click - add or remove current track.

        Edits the file in place: only the current track's lines change.
        """
        if not self.current_track:
            QMessageBox.information(self, "No Track Playing",
                                   "Please play a track first before managing playlists.")
            return

        playlist_path = item.data(Qt.UserRole)

        try:
            # Re-read from disk so edits made in other programs aren't lost
            m3u = M3UFile.read(playlist_path)

            if m3u.contains(self.current_track):
                removed = m3u.remove(self.current_track)
                self.logger.info(f'Removed {removed} entr{"y" if removed == 1 else "ies"} '
                                 f'from {playlist_path}')
            else:
                m3u.add(self.current_track_path)
                self.logger.info(f'Added {self.current_track_path} to {playlist_path}')

            m3u.write()
        except Exception as e:
            self.logger.error(f'Error updating playlist {playlist_path}: {e}')
            QMessageBox.warning(self, "Playlist Not Updated",
                                f"Couldn't update {os.path.basename(playlist_path)}:\n{e}")
            return

        self.playlists[playlist_path] = m3u.keys()

        # Add to recent playlists
        if self.config_manager:
            self.config_manager.add_recent_playlist(playlist_path, auto_save=True)

        self._update_highlighting()

    def _create_new_playlist(self):
        """Create a new empty playlist"""
        if not self.playlist_dir:
            return

        name, ok = QInputDialog.getText(self, "New Playlist", "Enter playlist name:")

        if not ok:
            return

        name = sanitize_filename(name)
        if not name:
            QMessageBox.warning(self, "Invalid Name",
                                "That name can't be used for a playlist.")
            return

        filename = f"{name}.m3u"
        playlist_path = os.path.join(self.playlist_dir, filename)

        if os.path.exists(playlist_path):
            if _same_path(playlist_path) in {_same_path(p) for p in self._hidden_playlists()}:
                QMessageBox.warning(self, "Playlist Exists",
                                    f"A playlist named '{name}' already exists but was "
                                    "removed from this profile. Use 'Add Playlists to "
                                    "Profile...' to bring it back.")
            else:
                QMessageBox.warning(self, "Playlist Exists",
                                    f"A playlist named '{name}' already exists.")
            return

        try:
            M3UFile.new(playlist_path).write()
        except Exception as e:
            self.logger.error(f'Error creating playlist {playlist_path}: {e}')
            QMessageBox.warning(self, "Playlist Not Created",
                                f"Couldn't create {filename}:\n{e}")
            return
        self.playlists[playlist_path] = []
        self._add_list_item(playlist_path)

    def set_current_track(self, file_path):
        """Update the current track and highlight playlists containing it"""
        self.current_track = track_key(file_path) if file_path else None
        self.current_track_path = file_path or None
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
                item.setBackground(theme.track_highlight())
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            else:
                item.setBackground(QBrush())  # theme's normal background
                font = item.font()
                font.setBold(False)
                item.setFont(font)
