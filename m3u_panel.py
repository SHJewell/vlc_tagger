import tkinter as tk
from tkinter import filedialog
import os
import logging

class M3UPanel:
    def __init__(self, parent, callback_play):
        self.logger = logging.getLogger(__name__)
        self.logger.debug('Initializing M3UPanel')

        self.parent = parent
        self.callback_play = callback_play
        self.playlist_files = []
        self.current_index = -1
        self.playlist_title = ""

        # Create main frame for M3U playlist
        self.frame = tk.Frame(parent, width=200)

        # Title label
        self.title_label = tk.Label(self.frame, text="M3U Playlists", font=("Arial", 10, "bold"))
        self.title_label.pack(fill=tk.X, padx=5, pady=(5, 0))

        # Create a button to select M3U file
        self.file_button = tk.Button(self.frame, text="Load M3U/M3U8", command=self.load_m3u_file)
        self.file_button.pack(fill=tk.X, padx=5, pady=5)

        # Playlist name display
        self.playlist_name_label = tk.Label(self.frame, text="No playlist loaded", wraplength=180)
        self.playlist_name_label.pack(fill=tk.X, padx=5)

        # Create a listbox to display playlist items
        self.list_frame = tk.Frame(self.frame)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=5)

        self.scrollbar = tk.Scrollbar(self.list_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.playlist_box = tk.Listbox(self.list_frame)
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Connect scrollbar to listbox
        self.playlist_box.config(yscrollcommand=self.scrollbar.set)
        self.scrollbar.config(command=self.playlist_box.yview)

        # Bind double-click to play selected file
        self.playlist_box.bind("<Double-Button-1>", self.play_selected)

        self.logger.debug('M3UPanel initialized')

    def load_m3u_file(self):
        """Open file dialog and load M3U/M3U8 playlist"""
        self.logger.debug('Selecting M3U playlist file')
        file_path = filedialog.askopenfilename(
            title="Select M3U Playlist",
            filetypes=[("M3U files", "*.m3u"), ("M3U8 files", "*.m3u8"), ("All files", "*.*")]
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
        self.playlist_box.delete(0, tk.END)
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
                    self.playlist_box.insert(tk.END, display_name)

                    # Reset current title for next track
                    current_title = None

            # Update playlist name display
            display_name = self.playlist_title if self.playlist_title else os.path.basename(file_path)
            self.playlist_name_label.config(text=display_name)

            self.logger.info(f'Loaded {len(self.playlist_files)} items from M3U playlist')

        except Exception as e:
            self.logger.error(f'Error parsing M3U file: {e}')
            self.playlist_name_label.config(text="Error loading playlist")

    def add_to_playlist(self, file_path):
        """Add a single file to the playlist (for compatibility)"""
        if file_path not in self.playlist_files:
            self.playlist_files.append(file_path)
            filename = os.path.basename(file_path)
            self.playlist_box.insert(tk.END, filename)
            self.logger.debug(f'Added {filename} to M3U playlist')

            # If this is the first file, set it as current
            if len(self.playlist_files) == 1:
                self.current_index = 0
                self.playlist_box.selection_set(0)
        else:
            # If the file is already in the playlist, select it only if this panel is being used
            index = self.playlist_files.index(file_path)
            self.current_index = index
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(index)
            self.playlist_box.see(index)
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
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(index)
            self.playlist_box.see(index)
            self.logger.debug(f'Updated M3U visual selection to index {index}')

    def clear_visual_selection(self):
        """Clear the visual selection in this panel"""
        self.playlist_box.selection_clear(0, tk.END)

    def play_selected(self, event=None):
        """Play the selected file in the playlist"""
        selection = self.playlist_box.curselection()
        if selection:
            index = selection[0]
            self.current_index = index
            self.logger.debug(f'Selected M3U item at index {index}: {self.playlist_files[index]}')
            self.callback_play(self.playlist_files[index])
            # Highlight the currently playing item
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(index)

    def next_track(self):
        """Play the next track in the playlist"""
        if not self.playlist_files:
            self.logger.debug('No tracks in M3U playlist')
            return None

        if self.current_index < len(self.playlist_files) - 1:
            self.current_index += 1
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(self.current_index)
            self.playlist_box.see(self.current_index)  # Ensure visible
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
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(self.current_index)
            self.playlist_box.see(self.current_index)  # Ensure visible
            self.logger.info(f'Moving to previous M3U track: {self.playlist_files[self.current_index]}')
            return self.playlist_files[self.current_index]
        else:
            self.logger.info('Already at first M3U track')
            return None
