import tkinter as tk
from tkinter import filedialog
import vlc
import logging
from playlist_panel import PlaylistPanel
from m3u_panel import M3UPanel

class SimpleVideoPlayer:
    def __init__(self, root):
        # Set up logger to log to a file
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("vlc_tagger.log", encoding="utf-8"),
                logging.StreamHandler()
            ]
        )
        self.logger.debug('Initializing SimpleVideoPlayer')

        self.root = root
        self.root.title("Simple Video Player")

        # Create the main frame to hold everything
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Create side-by-side layout
        self.content_frame = tk.Frame(self.main_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        # Create a canvas to hold the video
        self.canvas = tk.Canvas(self.content_frame, width=800, height=600)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Create right sidebar for both playlist panels
        self.sidebar_frame = tk.Frame(self.content_frame, width=250)
        self.sidebar_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)  # Maintain fixed width

        # Folder playlist panel (top half)
        self.playlist_panel = PlaylistPanel(self.sidebar_frame, self.play_file)
        self.playlist_panel.frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=2, pady=(2, 1))

        # M3U playlist panel (bottom half)
        self.m3u_panel = M3UPanel(self.sidebar_frame, self.play_file)
        self.m3u_panel.frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=2, pady=(1, 2))

        # Track which panel is currently active
        self.active_panel = 'folder'  # 'folder' or 'm3u'

        # Frame for buttons (controls)
        self.controls_frame = tk.Frame(self.main_frame)
        self.controls_frame.pack(fill=tk.X)

        # VLC instance and media player
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

        # Open button
        self.open_button = tk.Button(self.controls_frame, text="Open Video", command=self.open_file)
        self.open_button.pack(side=tk.LEFT)

        # Play/Pause button
        self.play_pause_button = tk.Button(self.controls_frame, text="Play", command=self.play_pause)
        self.play_pause_button.pack(side=tk.LEFT)

        # Stop button
        self.stop_button = tk.Button(self.controls_frame, text="Stop", command=self.stop)
        self.stop_button.pack(side=tk.LEFT)

        # Previous Track button
        self.prev_button = tk.Button(self.controls_frame, text="Previous", command=self.previous_track)
        self.prev_button.pack(side=tk.LEFT)

        # Next Track button
        self.next_button = tk.Button(self.controls_frame, text="Next", command=self.next_track)
        self.next_button.pack(side=tk.LEFT)

        # Mute button
        self.mute_button = tk.Button(self.controls_frame, text="Mute", command=self.mute)
        self.mute_button.pack(side=tk.LEFT)

        # Volume controls
        self.volume_label = tk.Label(self.controls_frame, text="Volume")
        self.volume_label.pack(side=tk.LEFT)
        self.volume_slider = tk.Scale(self.controls_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.set_volume)
        self.volume_slider.set(100)
        self.volume_slider.pack(side=tk.LEFT)

        # Time bar (seek bar) - bind to drag events instead of command
        self.time_slider = tk.Scale(self.controls_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=300)
        self.time_slider.pack(side=tk.LEFT)
        self.time_slider.bind("<ButtonRelease-1>", self.on_seek_release)
        self.time_slider.bind("<Button-1>", self.on_seek_start)

        self.updating_slider = False
        self.seeking = False
        self.root.after(500, self.update_time_slider)

    def open_file(self):
        self.logger.debug('Open file dialog triggered')
        file_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.avi *.mkv")])
        if file_path:
            self.logger.info(f'File selected: {file_path}')
            # Add to folder playlist
            self.playlist_panel.add_to_playlist(file_path)
            self.play_file(file_path)
        else:
            self.logger.info('No file selected')

    def play_file(self, file_path):
        """Play a specific file"""
        self.logger.info(f'Playing file: {file_path}')

        # Determine which panel contains the file and set it as active
        in_folder_panel = file_path in self.playlist_panel.playlist_files
        in_m3u_panel = file_path in self.m3u_panel.playlist_files

        if in_folder_panel and in_m3u_panel:
            # File is in both panels - use the currently active panel
            if self.active_panel == 'folder':
                self.playlist_panel.update_visual_selection(file_path)
                self.m3u_panel.set_current_file(file_path)  # Track internally only
                self.m3u_panel.clear_visual_selection()
            else:
                self.m3u_panel.update_visual_selection(file_path)
                self.playlist_panel.set_current_file(file_path)  # Track internally only
                self.playlist_panel.clear_visual_selection()
        elif in_folder_panel:
            # File only in folder panel
            self.active_panel = 'folder'
            self.playlist_panel.update_visual_selection(file_path)
            self.m3u_panel.clear_visual_selection()
            self.logger.debug('Set active panel to folder playlist')
        elif in_m3u_panel:
            # File only in M3U panel
            self.active_panel = 'm3u'
            self.m3u_panel.update_visual_selection(file_path)
            self.playlist_panel.clear_visual_selection()
            self.logger.debug('Set active panel to M3U playlist')
        else:
            # File not in either panel - clear both visual selections
            self.playlist_panel.clear_visual_selection()
            self.m3u_panel.clear_visual_selection()

        self.player.set_xwindow(self.canvas.winfo_id())
        media = self.instance.media_new(file_path)
        self.player.set_media(media)
        self.player.play()
        self.play_pause_button.config(text="Pause")

    def play_pause(self):
        self.logger.debug('Play/Pause button pressed')
        is_playing = self.player.is_playing()
        if is_playing:
            self.logger.info('Pausing playback')
            self.player.pause()
            self.play_pause_button.config(text="Play")
        else:
            self.logger.info('Starting playback')
            self.player.play()
            self.play_pause_button.config(text="Pause")

    def stop(self):
        self.logger.debug('Stop button pressed')
        self.player.stop()

    def previous_track(self):
        self.logger.debug('Previous track button pressed')

        # Try the active panel first, then fall back to the other panel
        prev_track = None
        if self.active_panel == 'folder':
            prev_track = self.playlist_panel.previous_track()
            if not prev_track:
                prev_track = self.m3u_panel.previous_track()
        else:
            prev_track = self.m3u_panel.previous_track()
            if not prev_track:
                prev_track = self.playlist_panel.previous_track()

        if prev_track:
            self.play_file(prev_track)
        else:
            self.logger.info('No previous track available')

    def next_track(self):
        self.logger.debug('Next track button pressed')

        # Try the active panel first, then fall back to the other panel
        next_track = None
        if self.active_panel == 'folder':
            next_track = self.playlist_panel.next_track()
            if not next_track:
                next_track = self.m3u_panel.next_track()
        else:
            next_track = self.m3u_panel.next_track()
            if not next_track:
                next_track = self.playlist_panel.next_track()

        if next_track:
            self.play_file(next_track)
        else:
            self.logger.info('No next track available')

    def mute(self):
        self.logger.debug('Mute button pressed')
        is_muted = self.player.audio_get_mute()
        self.player.audio_toggle_mute()
        if is_muted:
            self.logger.info('Audio unmuted')
            self.mute_button.config(text="Mute")
        else:
            self.logger.info('Audio muted')
            self.mute_button.config(text="Unmute")

    def set_volume(self, value):
        volume = int(value)
        self.logger.debug(f'Setting volume to {volume}')
        self.player.audio_set_volume(volume)
        self.logger.info(f'Volume set to {volume}')

    def seek(self, value):
        if self.player.get_length() > 0:
            self.updating_slider = True
            seek_time = int(float(value) / 100 * self.player.get_length())
            self.logger.debug(f'Seeking to {seek_time} ms')
            self.player.set_time(seek_time)
            self.updating_slider = False

    def on_seek_start(self, event):
        """Called when user starts dragging the time slider"""
        self.seeking = True

    def on_seek_release(self, event):
        """Called when user releases the time slider"""
        if self.player.get_length() > 0:
            value = self.time_slider.get()
            seek_time = int(float(value) / 100 * self.player.get_length())
            self.logger.debug(f'Seeking to {seek_time} ms')
            self.player.set_time(seek_time)
        self.seeking = False

    def update_time_slider(self):
        if self.player.get_length() > 0 and not self.updating_slider and not self.seeking:
            pos = self.player.get_time() / self.player.get_length() * 100
            self.time_slider.set(pos)
        self.root.after(500, self.update_time_slider)

    def on_close(self):
        self.logger.info('Closing application, releasing VLC player')
        try:
            self.player.stop()
            self.player.release()
            self.instance.release()
        except Exception as e:
            self.logger.error(f'Error releasing VLC resources: {e}')
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleVideoPlayer(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
