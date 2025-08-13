import tkinter as tk
from tkinter import filedialog
import os
import logging

class PlaylistPanel:
    def __init__(self, parent, callback_play):
        self.logger = logging.getLogger(__name__)
        self.logger.debug('Initializing PlaylistPanel')

        self.parent = parent
        self.callback_play = callback_play
        self.playlist_files = []
        self.current_index = -1

        # Create main frame for playlist
        self.frame = tk.Frame(parent, width=200)

        # Create a button to select folder
        self.folder_button = tk.Button(self.frame, text="Select Folder", command=self.select_folder)
        self.folder_button.pack(fill=tk.X, padx=5, pady=5)

        # Create a listbox to display files
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

        self.logger.debug('PlaylistPanel initialized')

    def select_folder(self):
        """Open folder dialog and load video files into playlist"""
        self.logger.debug('Selecting folder for playlist')
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.logger.info(f'Folder selected: {folder_path}')
            self.load_playlist(folder_path)
        else:
            self.logger.info('No folder selected')

    def load_playlist(self, folder_path):
        """Load all video files from the selected folder"""
        self.logger.debug(f'Loading playlist from {folder_path}')

        # Clear current playlist
        self.playlist_box.delete(0, tk.END)
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
                    self.playlist_box.insert(tk.END, file)  # Show just the filename

            self.logger.info(f'Loaded {len(self.playlist_files)} video files')
        except Exception as e:
            self.logger.error(f'Error loading playlist: {e}')

    def add_to_playlist(self, file_path):
        """Add a single file to the playlist"""
        if file_path not in self.playlist_files:
            self.playlist_files.append(file_path)
            filename = os.path.basename(file_path)
            self.playlist_box.insert(tk.END, filename)
            self.logger.debug(f'Added {filename} to playlist')

            # If this is the first file, set it as current
            if len(self.playlist_files) == 1:
                self.current_index = 0
                self.playlist_box.selection_set(0)
        else:
            # If the file is already in the playlist, select it
            index = self.playlist_files.index(file_path)
            self.current_index = index
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(index)
            self.playlist_box.see(index)
            self.logger.debug(f'File already in playlist, selected at index {index}')

    def play_selected(self, event=None):
        """Play the selected file in the playlist"""
        selection = self.playlist_box.curselection()
        if selection:
            index = selection[0]
            self.current_index = index
            self.logger.debug(f'Selected file at index {index}: {self.playlist_files[index]}')
            self.callback_play(self.playlist_files[index])
            # Highlight the currently playing item
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(index)

    def next_track(self):
        """Play the next track in the playlist"""
        if not self.playlist_files:
            self.logger.debug('No tracks in playlist')
            return None

        if self.current_index < len(self.playlist_files) - 1:
            self.current_index += 1
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(self.current_index)
            self.playlist_box.see(self.current_index)  # Ensure visible
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
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(self.current_index)
            self.playlist_box.see(self.current_index)  # Ensure visible
            self.logger.info(f'Moving to previous track: {self.playlist_files[self.current_index]}')
            return self.playlist_files[self.current_index]
        else:
            self.logger.info('Already at first track')
            return None
