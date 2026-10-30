"""
Current Playlist Panel - Shows the current playlist or directory being played
"""
from PyQt5.QtWidgets import (QWidget, QDialog, QStackedWidget, QListView, QLineEdit,
                             QLabel, QFileDialog, QVBoxLayout, QMenu, QAbstractItemView,
                             QTreeWidget, QTreeWidgetItem, QHeaderView, QAction)

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QCursor
import os
import re
import logging
import random

from typing import Optional

from m3u_file import M3UFile
from media_info import MediaInfoLoader, format_length

# Media file extensions
MEDIA_EXTENSIONS = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
                    '.mp3', '.wav', '.flac', '.ogg', '.m4a')

PLAYLIST_EXTENSIONS = ('.m3u', '.m3u8')

# Playlist table columns: (column, config key, header label)
COL_NAME, COL_ARTIST, COL_ALBUM, COL_LENGTH = range(4)
COLUMNS = [(COL_NAME, 'name', 'File Name'),
           (COL_ARTIST, 'artist', 'Artist'),
           (COL_ALBUM, 'album', 'Album'),
           (COL_LENGTH, 'length', 'Length')]
OPTIONAL_COLUMNS = (COL_ARTIST, COL_ALBUM, COL_LENGTH)   # File Name is always shown
COLUMN_KEYS = {col: key for col, key, _ in COLUMNS}

# Data stored on each row (in the File Name column)
PATH_ROLE = Qt.UserRole              # the file's path, as played
ORDER_ROLE = Qt.UserRole + 1         # position in the playlist file / folder
LENGTH_ROLE = Qt.UserRole + 2        # length in ms, for sorting (-1 = unknown)


def getOpenFilesAndDirs(parent=None, caption='', directory='',
                        filter='', initialFilter='', options=None):
    # Source - https://stackoverflow.com/a/64340482
    # Posted by musicamante
    # Retrieved 2026-02-11, License - CC BY-SA 4.0
    def updateText():
        selected = view.selectionModel().selectedRows()
        if selected:
            lineEdit.setText(selected[0].data())

    dialog = QFileDialog(parent, windowTitle=caption)
    dialog.setFileMode(dialog.AnyFile)
    if options:
        dialog.setOptions(options)
    dialog.setOption(dialog.DontUseNativeDialog, True)
    if directory:
        dialog.setDirectory(directory)
    if filter:
        dialog.setNameFilter(filter)
        if initialFilter:
            dialog.selectNameFilter(initialFilter)

    # by default, if a directory is opened in file listing mode,
    # QFileDialog.accept() shows the contents of that directory, but we
    # need to be able to "open" directories as we can do with files, so we
    # just override accept() with the default QDialog implementation which
    # will just return exec_()
    dialog.accept = lambda: QDialog.accept(dialog)

    # there are many item views in a non-native dialog, but the ones displaying
    # the actual contents are created inside a QStackedWidget; they are a
    # QTreeView and a QListView, and the tree is only used when the
    # viewMode is set to QFileDialog.Details, which is not this case
    stackedWidget = dialog.findChild(QStackedWidget)
    view = stackedWidget.findChild(QListView)
    view.selectionModel().selectionChanged.connect(updateText)

    lineEdit = dialog.findChild(QLineEdit)
    # clear the line edit contents whenever the current directory changes
    dialog.directoryEntered.connect(lambda: lineEdit.setText(''))

    # On Cancel, selectedFiles() still returns the browsed folder, so the
    # dialog result has to be checked explicitly
    if dialog.exec_() != QDialog.Accepted:
        return None
    selected = dialog.selectedFiles()
    return selected[0] if selected else None


def _hover_path(path):
    """Hover text for a list entry: the absolute path (stream URLs as-is)"""
    return path if '://' in path else os.path.abspath(path)


def _natural_key(text):
    """Sort key where 'Track 2' comes before 'Track 10' (case ignored)"""
    return [(0, int(part)) if part.isdigit() else (1, part)
            for part in re.split(r'(\d+)', text.casefold())]


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

        self._items_by_path = {}     # path -> its rows (a playlist can repeat a file)
        self._info_waiting = set()   # paths whose artist/album/length are still loading
        self._sort_column = None     # None = playlist order
        self._sort_order = Qt.AscendingOrder
        self._applying_view = False

        self.media_info = MediaInfoLoader(self)
        self.media_info.info_ready.connect(self._on_info_ready)

        self._setup_ui()
        self.apply_view_settings()

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

        # Playlist name
        self.playlist_name_label = QLabel("No playlist loaded")
        self.playlist_name_label.setWordWrap(True)
        self.playlist_name_label.setStyleSheet("font-style: italic; color: gray;")
        layout.addWidget(self.playlist_name_label)

        # File table
        self.file_list = QTreeWidget()
        self.file_list.setColumnCount(len(COLUMNS))
        self.file_list.setHeaderLabels([label for _, _, label in COLUMNS])
        self.file_list.headerItem().setTextAlignment(COL_LENGTH, Qt.AlignRight | Qt.AlignVCenter)
        self.file_list.setRootIsDecorated(False)
        self.file_list.setUniformRowHeights(True)
        self.file_list.setAllColumnsShowFocus(True)
        self.file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        # Enable tooltips on hover
        self.file_list.setMouseTracking(True)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.file_list)

        # Header: click to sort, right-click to choose columns
        header = self.file_list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for col, width in ((COL_ARTIST, 140), (COL_ALBUM, 140), (COL_LENGTH, 60)):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            header.resizeSection(col, width)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)
        header.sectionClicked.connect(self._on_header_clicked)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

        # Column on/off switches, shared by the header menu and View menu
        self.column_actions = {}
        for col, _, label in COLUMNS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(col)
            if col == COL_NAME:
                action.setChecked(True)
                action.setEnabled(False)
            else:
                action.toggled.connect(self._on_column_action_toggled)
            self.column_actions[col] = action
            self.file_list.setColumnHidden(col, col != COL_NAME)

        self.playlist_order_action = QAction("Sort by Playlist Order", self)
        self.playlist_order_action.triggered.connect(self._restore_playlist_order)
        self.playlist_order_action.setEnabled(False)

    # ---- Columns and sorting ----

    def add_view_actions(self, menu):
        """Put the column switches and sort reset into a menu"""
        for col, _, _ in COLUMNS:
            menu.addAction(self.column_actions[col])
        menu.addSeparator()
        menu.addAction(self.playlist_order_action)

    def _on_header_context_menu(self, _pos):
        self.logger.debug('Header right-click: opening column menu')
        # QCursor.pos() is already in screen coordinates; no header mapping needed
        self._show_view_menu(QCursor.pos())

    def _show_view_menu(self, global_pos):
        menu = QMenu(self)
        self.add_view_actions(menu)
        menu.exec_(global_pos)
        menu.deleteLater()   # one menu per right-click; don't let them pile up
        self.logger.debug('Column menu closed')

    def _on_column_action_toggled(self, visible):
        action = self.sender()
        if action is None:
            return
        self._set_column_visible(action.data(), visible)

    def apply_view_settings(self):
        """Show the columns and sort saved in the active profile"""
        columns, sort = [], None
        if self.config_manager:
            columns = self.config_manager.get('playlist_columns') or []
            sort = self.config_manager.get('playlist_sort')

        self._applying_view = True
        try:
            for col in OPTIONAL_COLUMNS:
                self.column_actions[col].setChecked(COLUMN_KEYS[col] in columns)
                self.file_list.setColumnHidden(col, COLUMN_KEYS[col] not in columns)

            self._sort_column = None
            if isinstance(sort, dict):
                keys = {key: col for col, key in COLUMN_KEYS.items()}
                col = keys.get(sort.get('column'))
                if col is not None and not self.file_list.isColumnHidden(col):
                    self._sort_column = col
                    self._sort_order = (Qt.DescendingOrder if sort.get('descending')
                                        else Qt.AscendingOrder)
            self._apply_sort()
        finally:
            self._applying_view = False
        self._request_info()

    def _save_view_settings(self):
        if self._applying_view or not self.config_manager:
            return
        columns = [COLUMN_KEYS[col] for col in OPTIONAL_COLUMNS
                   if not self.file_list.isColumnHidden(col)]
        sort = None
        if self._sort_column is not None:
            sort = {'column': COLUMN_KEYS[self._sort_column],
                    'descending': self._sort_order == Qt.DescendingOrder}
        self.config_manager.set('playlist_columns', columns)
        self.config_manager.set('playlist_sort', sort, auto_save=True)

    def _set_column_visible(self, col, visible):
        self.logger.debug(f'Column {COLUMN_KEYS[col]} -> {"shown" if visible else "hidden"}')
        self.file_list.setColumnHidden(col, not visible)
        if visible:
            self._request_info()
        elif col == self._sort_column:
            # Don't stay sorted by a column you can't see
            self._sort_column = None
            self._apply_sort()
        self._save_view_settings()

    def _on_header_clicked(self, col):
        """Sort by the clicked column; clicking it again reverses the order"""
        if col == self._sort_column:
            self._sort_order = (Qt.AscendingOrder if self._sort_order == Qt.DescendingOrder
                                else Qt.DescendingOrder)
        else:
            self._sort_column = col
            self._sort_order = Qt.AscendingOrder
        self._apply_sort()
        self._save_view_settings()

    def _restore_playlist_order(self):
        self._sort_column = None
        self._apply_sort()
        self._save_view_settings()

    def _sort_key(self, item):
        if self._sort_column == COL_LENGTH:
            length = item.data(COL_NAME, LENGTH_ROLE)
            return -1 if length is None else length
        return _natural_key(item.text(self._sort_column))

    def _apply_sort(self):
        """Reorder the rows. Playback (next/previous) follows the shown order,
        so the file list, current index and shuffle history are rebuilt too."""
        header = self.file_list.header()
        if self._sort_column is None:
            header.setSortIndicatorShown(False)
        else:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(self._sort_column, self._sort_order)
        self.playlist_order_action.setEnabled(self._sort_column is not None)

        count = self.file_list.topLevelItemCount()
        if not count:
            return
        self.logger.debug(f'Sorting {count} rows by '
                          f'{COLUMN_KEYS.get(self._sort_column, "playlist order")}')

        selected = self.file_list.currentItem()
        items = [self.file_list.takeTopLevelItem(i) for i in reversed(range(count))]
        items.reverse()
        current = items[self.current_index] if 0 <= self.current_index < count else None
        history = [items[i] for i in self.shuffle_history if 0 <= i < count]

        # Start from playlist order so ties keep it (sorted() is stable)
        items.sort(key=lambda it: it.data(COL_NAME, ORDER_ROLE))
        if self._sort_column is not None:
            items.sort(key=self._sort_key,
                       reverse=self._sort_order == Qt.DescendingOrder)

        self.file_list.addTopLevelItems(items)
        row_of = {id(item): row for row, item in enumerate(items)}
        self.playlist_files = [item.data(COL_NAME, PATH_ROLE) for item in items]
        self.logger.debug('Sort done')
        self.current_index = row_of[id(current)] if current is not None else -1
        self.shuffle_history = [row_of[id(item)] for item in history]

        if selected is not None:
            self.file_list.setCurrentItem(selected)
            self.file_list.scrollToItem(selected)

    # ---- Rows and file info ----

    def _add_row(self, path, name):
        """Append a row for path (also appends it to playlist_files)"""
        item = QTreeWidgetItem([name or path, '', '', ''])
        item.setData(COL_NAME, PATH_ROLE, path)
        item.setData(COL_NAME, ORDER_ROLE, len(self.playlist_files))
        item.setTextAlignment(COL_LENGTH, Qt.AlignRight | Qt.AlignVCenter)
        tip = _hover_path(path)
        for col in range(len(COLUMNS)):
            item.setToolTip(col, tip)

        info = self.media_info.cached(path)
        if info:
            self._fill_info(item, info)

        self.playlist_files.append(path)
        self.file_list.addTopLevelItem(item)
        self._items_by_path.setdefault(path, []).append(item)

    @staticmethod
    def _fill_info(item, info):
        item.setText(COL_ARTIST, info['artist'])
        item.setText(COL_ALBUM, info['album'])
        item.setText(COL_LENGTH, format_length(info['length_ms']))
        item.setData(COL_NAME, LENGTH_ROLE, info['length_ms'])

    def _request_info(self):
        """Start reading artist/album/length, if any of those columns is shown"""
        if all(self.file_list.isColumnHidden(col) for col in OPTIONAL_COLUMNS):
            return
        paths = [p for p in self._items_by_path
                 if '://' not in p and self.media_info.cached(p) is None]
        self._info_waiting = set(paths)
        self.logger.debug(f'Reading file info for {len(paths)} files')
        self.media_info.request(paths)

    def _on_info_ready(self, path, info):
        for item in self._items_by_path.get(path, []):
            self._fill_info(item, info)

        if path in self._info_waiting:
            self._info_waiting.discard(path)
            # Sorted by a column that was still loading: sort again now it's all in
            if not self._info_waiting and self._sort_column in OPTIONAL_COLUMNS:
                self._apply_sort()

    def _select_row(self, row):
        item = self.file_list.topLevelItem(row)
        if item is not None:
            self.file_list.setCurrentItem(item)

    def _save_index(self, auto_save=False):
        """Save the current track's position in playlist order (startup restores
        the playlist in that order, then re-applies the sort)"""
        if not self.config_manager:
            return
        item = self.file_list.topLevelItem(self.current_index) \
            if 0 <= self.current_index < len(self.playlist_files) else None
        order = item.data(COL_NAME, ORDER_ROLE) if item is not None else -1
        self.config_manager.set_current_playlist_index(order, auto_save=auto_save)

    def _finish_loading(self):
        """After rows are added: apply the sort and start reading file info"""
        self._apply_sort()
        self._request_info()

    def _show_context_menu(self, position):
        """Right-click menu for the current playlist"""
        menu = QMenu(self)
        go_action = menu.addAction("Go to Current File", self.scroll_to_current)
        go_action.setEnabled(0 <= self.current_index < len(self.playlist_files))
        menu.addSeparator()
        menu.addAction("Load Playlist/Folder...", self._load_current_playlist)
        menu.exec_(self.file_list.mapToGlobal(position))

    def scroll_to_current(self):
        """Select the playing file and scroll it into the middle of the list"""
        if not 0 <= self.current_index < len(self.playlist_files):
            return
        item = self.file_list.topLevelItem(self.current_index)
        # Drop whatever the user clicked since, then re-highlight the playing file
        self.file_list.clearSelection()
        self.file_list.setCurrentItem(item)
        item.setSelected(True)
        self.file_list.scrollToItem(item, QAbstractItemView.PositionAtCenter)
        self.file_list.setFocus()

    def _load_current_playlist(self):
        """Load either a folder or M3U playlist"""

        file = getOpenFilesAndDirs(
            parent=self,
            caption="Select Folder or M3U Playlist",
            filter="M3U Playlists (*.m3u *.m3u8);;All Files (*)"
        )

        if file:
            if os.path.isdir(file):
                # It's a folder
                self._load_folder(file)
            elif file.lower().endswith(('.m3u', '.m3u8')):
                # It's an M3U file
                self._load_m3u(file)
            else:
                self.logger.warning(f"Unsupported selection: {file}")

        return None

    def _load_folder(self, path: Optional[str] = None, autoplay=True):
        """Load all media files from a selected folder"""

        if path:
            self.logger.info(f'Loading folder: {path}')
            self._clear_playlist()

            self.current_folder = path

            try:
                files = os.listdir(path)

                for file in sorted(files):
                    if file.lower().endswith(MEDIA_EXTENSIONS):
                        self._add_row(os.path.join(path, file), file)
                self._finish_loading()

                self.playlist_name_label.setText(f"Folder: {os.path.basename(path)}")
                self.logger.info(f'Loaded {len(self.playlist_files)} files from folder')

                # Save to config — a folder load has no playlist file, so
                # explicitly clear any stale path (update_playlist_state
                # skips None values)
                if self.config_manager:
                    self.config_manager.set_current_playlist_path(None, auto_save=False)
                    self.config_manager.update_playlist_state(
                        index=0 if self.playlist_files else -1,
                        folder=path,
                        auto_save=True
                    )

                # Auto-play first file
                if self.playlist_files and autoplay:
                    self.current_index = 0
                    self._select_row(0)
                    if self.play_callback:
                        self.play_callback(self.playlist_files[0])

            except Exception as e:
                self.logger.error(f'Error loading folder: {e}')

    def _load_m3u(self, path: Optional[str] = None, autoplay=True):
        """Load M3U/M3U8 playlist file"""

        if path:
            self.logger.info(f'Loading M3U: {path}')
            self._clear_playlist()

            try:
                # Shared reader: detects encoding instead of dropping
                # non-UTF-8 characters
                m3u = M3UFile.read(path)
                playlist_dir = m3u.playlist_dir

                for track in m3u.tracks:
                    file_url = track.path
                    self._add_row(file_url, os.path.basename(file_url.rstrip('/\\')))
                self._finish_loading()

                self.playlist_name_label.setText(f"Playlist: {os.path.basename(path)}")
                self.logger.info(f'Loaded {len(self.playlist_files)} files from M3U')

                # Save to config
                if self.config_manager:
                    # Store the .m3u path itself, never the expanded track list
                    self.config_manager.update_playlist_state(
                        playlist_path=path,
                        index=0 if self.playlist_files else -1,
                        folder=playlist_dir,
                        auto_save=True
                    )
                    self.config_manager.add_recent_playlist(path, auto_save=True)

                # Auto-play first file
                if self.playlist_files and autoplay:
                    self.current_index = 0
                    self._select_row(0)
                    if self.play_callback:
                        self.play_callback(self.playlist_files[0])

            except Exception as e:
                self.logger.error(f'Error loading M3U: {e}')

    def _clear_playlist(self):
        """Clear the current playlist"""
        self.playlist_files.clear()
        self.file_list.clear()
        self._items_by_path = {}
        self._info_waiting = set()
        self.media_info.cancel_pending()
        self.current_index = -1
        self.shuffle_history.clear()
        self.current_folder = None
        self.playlist_name_label.setText("No playlist loaded")

        # Save cleared state to config (setters, not update_playlist_state,
        # because the latter skips None values)
        if self.config_manager:
            self.config_manager.set_current_playlist_path(None, auto_save=False)
            self.config_manager.set_current_folder(None, auto_save=False)
            self.config_manager.set_current_playlist_index(-1, auto_save=True)

    def _on_file_double_clicked(self, item, column=0):
        """Handle double-click on a file"""
        row = self.file_list.indexOfTopLevelItem(item)
        if 0 <= row < len(self.playlist_files):
            # Remember where we were so Previous in shuffle can come back
            if self.shuffle_mode and row != self.current_index:
                self._push_shuffle_history()
            self.current_index = row
            if self.play_callback:
                self.play_callback(self.playlist_files[row])

    def set_current_file(self, file_path):
        """Set the current file and update selection"""
        if file_path in self.playlist_files:
            self.current_index = self.playlist_files.index(file_path)
            self._select_row(self.current_index)

            # Update index in memory; play_file's save writes it to disk
            self._save_index()

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
            self._push_shuffle_history()
        else:
            # Normal sequential playback
            if self.current_index < len(self.playlist_files) - 1:
                next_index = self.current_index + 1
            else:
                return None  # End of playlist

        self.current_index = next_index
        self._select_row(next_index)

        # Update index in memory; play_file's save writes it to disk
        self._save_index()

        return self.playlist_files[next_index]

    def previous_track(self):
        """Get the previous track in the playlist"""
        if not self.playlist_files:
            return None

        # Go back in shuffle history, skipping any invalid entries (a stray
        # -1 would otherwise index from the end and play the last track)
        prev_index = None
        if self.shuffle_mode:
            while self.shuffle_history:
                candidate = self.shuffle_history.pop()
                if 0 <= candidate < len(self.playlist_files):
                    prev_index = candidate
                    break

        if prev_index is None:
            # Normal sequential playback
            if self.current_index > 0:
                prev_index = self.current_index - 1
            else:
                return None  # Start of playlist

        self.current_index = prev_index
        self._select_row(prev_index)

        # Update index in memory; play_file's save writes it to disk
        self._save_index()

        return self.playlist_files[prev_index]

    def _push_shuffle_history(self):
        """Record the current track for shuffle's Previous, if it's a real one"""
        if 0 <= self.current_index < len(self.playlist_files):
            self.shuffle_history.append(self.current_index)

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

    def restore_playlist(self, playlist_path, index, folder, autoplay=False):
        """
        Restore playlist state from saved config

        Args:
            playlist_files: List of file paths
            index: Current playlist index
            folder: Current folder path
        """
        self.logger.info(f'Restoring playlist from {playlist_path}')

        # Clear current playlist first
        self._clear_playlist()

        # Restore files
        if playlist_path and os.path.isfile(playlist_path) and playlist_path.lower().endswith(('.m3u', '.m3u8')):
            self._load_m3u(playlist_path, autoplay=autoplay)
        elif playlist_path and os.path.isfile(playlist_path) and not playlist_path.lower().endswith(('.m3u', '.m3u8')):
            self._load_folder(os.path.dirname(playlist_path), autoplay=autoplay)
        elif folder and os.path.exists(folder):
            self._load_folder(folder, autoplay=autoplay)
        elif playlist_path and os.path.isdir(playlist_path):
            self._load_folder(playlist_path, autoplay=autoplay)
        else:
            self.logger.info('No valid playlist or folder to restore')
            return

        # _load_m3u/_load_folder already populated (and sorted) the rows; the
        # saved index is a position in playlist order, so find where it is now
        self.current_index = -1
        for row in range(self.file_list.topLevelItemCount()):
            if self.file_list.topLevelItem(row).data(COL_NAME, ORDER_ROLE) == index:
                self.current_index = row
                break
        self.current_folder = folder

        # Set current selection
        if 0 <= self.current_index < len(self.playlist_files):
            self._select_row(self.current_index)

        # Update label
        if folder:
            self.playlist_name_label.setText(f"{os.path.basename(folder)} - {len(self.playlist_files)} files")
            self.playlist_name_label.setToolTip(f"<b>{folder}</b>")
        elif self.playlist_files:
            self.playlist_name_label.setText(f"{os.path.basename(playlist_path)} - {len(self.playlist_files)} files")
            self.playlist_name_label.setToolTip(f"<b>{playlist_path}</b>")
        else:
            self.playlist_name_label.setText("No playlist loaded")
            self.playlist_name_label.setToolTip("")

        self.logger.info(f'Playlist restored with index {self.current_index}')

