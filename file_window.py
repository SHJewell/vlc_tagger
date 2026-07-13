"""
File Window - Contains current playlist and playlist manager panels
"""
from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QAction, QFileDialog, QSplitter, QDialog, QLabel,
                             QListWidget, QListWidgetItem, QPushButton,
                             QInputDialog, QMessageBox)
from PyQt5.QtCore import Qt
import logging

from current_playlist_panel import CurrentPlaylistPanel
from playlist_manager_panel import PlaylistManagerPanel

import app_registry


class FileWindow(QMainWindow):
    """File window for managing playlists and viewing current playlist"""

    def __init__(self, player_window=None, config_manager=None):
        super().__init__()

        self.logger = logging.getLogger(__name__)
        self.logger.debug('Initializing FileWindow')

        self.player_window = player_window

        self.config_manager = config_manager

        if config_manager is None:
            self.config_manager = app_registry.get('config_manager')

        self.setWindowTitle("Playlist Manager")
        self.setGeometry(920, 100, 600, 800)

        self._setup_ui()
        self._update_window_title()

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

        load_playlist_action = QAction('Load Playlist/Folder...', self)
        load_playlist_action.triggered.connect(self.current_playlist_panel._load_current_playlist)
        file_menu.addAction(load_playlist_action)

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

        profile_menu = menubar.addMenu('Profiles')

        new_profile_action = QAction('New Profile...', self)
        new_profile_action.triggered.connect(self._new_profile)
        profile_menu.addAction(new_profile_action)

        switch_profile_action = QAction('Switch Profile...', self)
        switch_profile_action.triggered.connect(self._switch_profile)
        profile_menu.addAction(switch_profile_action)

        delete_profile_action = QAction('Delete Profile...', self)
        delete_profile_action.triggered.connect(self._delete_profile)
        profile_menu.addAction(delete_profile_action)

        profile_menu.addSeparator()

        save_config_action = QAction('Save Config', self)
        save_config_action.triggered.connect(self.config_manager.save)
        profile_menu.addAction(save_config_action)

    def _update_window_title(self):
        """Show the active profile in the window title"""
        if self.config_manager:
            self.setWindowTitle(f"Playlist Manager — {self.config_manager.profile_name}")

    def _pick_profile(self, title, prompt, profiles=None):
        """Show a list dialog to pick a profile; returns the name or None"""
        if profiles is None:
            profiles = self.config_manager.list_profiles()

        if not profiles:
            QMessageBox.information(self, "No Profiles", "No configuration profiles found.")
            return None

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(300, 250)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(prompt))

        profile_list = QListWidget()
        for profile in profiles:
            item = QListWidgetItem(profile)
            profile_list.addItem(item)
            # Pre-select the current profile
            if profile == self.config_manager.profile_name:
                profile_list.setCurrentItem(item)

        layout.addWidget(profile_list)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Enable OK button only when a profile is selected
        ok_btn.setEnabled(profile_list.currentItem() is not None)
        profile_list.currentItemChanged.connect(
            lambda current, _: ok_btn.setEnabled(current is not None)
        )

        # Allow double-click to accept
        profile_list.itemDoubleClicked.connect(lambda _: ok_btn.click())

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() != QDialog.Accepted:
            return None

        selected = profile_list.currentItem()
        return selected.text() if selected else None

    def _apply_active_profile(self):
        """Have the app re-apply the active profile to all windows"""
        app = app_registry.get('app')
        if app:
            app.apply_profile()
        self._update_window_title()

    def _new_profile(self):
        """Create a new profile and switch to it"""
        name, ok = QInputDialog.getText(
            self, "New Profile", "Enter a name for the new profile:"
        )
        if not ok:
            return

        name = self.config_manager.sanitize_profile_name(name)
        if not name:
            QMessageBox.warning(self, "Invalid Name",
                                "That name can't be used for a profile.")
            return

        if name in self.config_manager.list_profiles():
            reply = QMessageBox.question(
                self, "Profile Exists",
                f"A profile named '{name}' already exists. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        reply = QMessageBox.question(
            self, "New Profile",
            "Keep the current files and folders in the new profile?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        if reply == QMessageBox.Cancel:
            return

        self.config_manager.create_profile(name, keep_files=(reply == QMessageBox.Yes))
        self._apply_active_profile()

    def _switch_profile(self):
        """Switch to another profile and apply it"""
        name = self._pick_profile("Switch Profile", "Select a profile to load:")
        if not name or name == self.config_manager.profile_name:
            return

        self.config_manager.save()  # Save current profile before switching
        self.config_manager.switch_profile(name)
        self._apply_active_profile()

    def _delete_profile(self):
        """Delete a profile (the active one is protected)"""
        profiles = [p for p in self.config_manager.list_profiles()
                    if p != self.config_manager.profile_name]
        if not profiles:
            QMessageBox.information(self, "Delete Profile",
                                    "There are no other profiles to delete.")
            return

        name = self._pick_profile("Delete Profile", "Select a profile to delete:",
                                  profiles=profiles)
        if not name:
            return

        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.config_manager.delete_profile(name)

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

