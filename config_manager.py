"""
Config Manager - Handles loading and saving application configuration
"""
import json
import os
import logging
from typing import Optional, Dict, Any, List


class ConfigManager:
    """Manages application configuration and persistence"""

    def __init__(self, config_dir: str = None, profile_name: str = "default"):
        """
        Initialize the config manager

        Args:
            config_dir: Directory to store config files. Defaults to ./config
            profile_name: Name of the profile to use (e.g., 'default', 'music')
        """
        self.logger = logging.getLogger(__name__)

        # Set config directory
        if config_dir is None:
            # Use 'config' directory in the current working directory
            config_dir = os.path.join(os.getcwd(), 'config')

        self.config_dir = config_dir
        self.profiles_dir = os.path.join(self.config_dir, 'profiles')
        self.profile_name = profile_name
        self.config_file = os.path.join(self.profiles_dir, f'{profile_name}.json')

        # Default configuration
        self.config = self._get_default_config()

        # Ensure directories exist
        self._ensure_directories()

        # Load existing config
        self.load()

        self.logger.info(f'Config manager initialized with profile: {profile_name}')

    def _ensure_directories(self):
        """Ensure config directories exist"""
        try:
            os.makedirs(self.profiles_dir, exist_ok=True)
            self.logger.debug(f'Config directory ensured: {self.profiles_dir}')
        except Exception as e:
            self.logger.error(f'Failed to create config directory: {e}')

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            # Playback settings
            'volume': 100,
            'current_file': None,
            'current_playlist_path': None,
            'current_folder': None,
            'last_position': 0.0,
            'shuffle_mode': False,

            # Directory settings
            'default_save_folder': None,
            'default_load_folder': None,
            'playlist_directory': None,
            'default_playlists': [],  # List of default playlist paths

            # Window positions
            'window_positions': {
                'player': {
                    'x': 100,
                    'y': 100,
                    'width': 800,
                    'height': 700
                },
                'file': {
                    'x': 920,
                    'y': 100,
                    'width': 600,
                    'height': 800
                }
            },

            # Recent items
            'recent_files': [],
            'recent_folders': [],
            'recent_playlists': [],

            # UI settings
            'theme': 'default',
            'current_playlist_index': -1
        }

    def load(self) -> bool:
        """
        Load configuration from file

        Returns:
            True if loaded successfully, False otherwise
        """
        if not os.path.exists(self.config_file):
            self.logger.info(f'Config file not found, using defaults: {self.config_file}')
            return False

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)

            # Merge loaded config with defaults (to handle new keys)
            self.config = self._merge_configs(self.config, loaded_config)

            self.logger.info(f'Config loaded from: {self.config_file}')
            return True

        except Exception as e:
            self.logger.error(f'Failed to load config: {e}')
            return False

    def save(self) -> bool:
        """
        Save configuration to file

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            self._ensure_directories()

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)

            self.logger.info(f'Config saved to: {self.config_file}')
            return True

        except Exception as e:
            self.logger.error(f'Failed to save config: {e}')
            return False

    def _merge_configs(self, default: Dict, loaded: Dict) -> Dict:
        """
        Merge loaded config with default config

        Args:
            default: Default configuration
            loaded: Loaded configuration

        Returns:
            Merged configuration
        """
        result = default.copy()

        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge dictionaries
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    # Getters
    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value"""
        return self.config.get(key, default)

    def get_volume(self) -> int:
        """Get saved volume level (0-100)"""
        return self.config.get('volume', 100)

    def get_current_file(self) -> Optional[str]:
        """Get the current file path"""
        return self.config.get('current_file')

    def get_current_folder(self) -> Optional[str]:
        """Get the current folder path"""
        return self.config.get('current_folder')

    def get_current_playlist_path(self) -> Optional[str]:
        """Get the current playlist files"""
        return self.config.get('current_playlist_path', )

    def get_current_playlist_index(self) -> int:
        """Get the current playlist index"""
        return self.config.get('current_playlist_index', -1)

    def get_last_position(self) -> float:
        """Get the last playback position"""
        return self.config.get('last_position', 0.0)

    def get_shuffle_mode(self) -> bool:
        """Get shuffle mode state"""
        return self.config.get('shuffle_mode', False)

    def get_window_position(self, window_name: str) -> Optional[Dict[str, int]]:
        """Get window position and size"""
        return self.config.get('window_positions', {}).get(window_name)

    def get_recent_files(self, max_count: int = 10) -> List[str]:
        """Get recent files list"""
        recent = self.config.get('recent_files', [])
        return recent[:max_count]

    def get_recent_folders(self, max_count: int = 10) -> List[str]:
        """Get recent folders list"""
        recent = self.config.get('recent_folders', [])
        return recent[:max_count]

    def get_recent_playlists(self, max_count: int = 10) -> List[str]:
        """Get recent playlists list"""
        recent = self.config.get('recent_playlists', [])
        return recent[:max_count]

    def get_default_load_folder(self) -> Optional[str]:
        """Get default folder for loading files"""
        return self.config.get('default_load_folder')

    def get_playlist_directory(self) -> Optional[str]:
        """Get playlist directory"""
        return self.config.get('playlist_directory')

    def get_default_playlists(self) -> List[str]:
        """Get list of default playlists"""
        return self.config.get('default_playlists', [])

    def get_autoplay_on_launch(self):
        """Get autoplay on launch setting"""
        return self.config.get('autoplay_on_launch', False)

    # Setters
    def set(self, key: str, value: Any, auto_save: bool = False):
        """Set a config value"""
        self.config[key] = value
        if auto_save:
            self.save()

    def set_volume(self, volume: int, auto_save: bool = True):
        """Set volume level (0-100)"""
        self.config['volume'] = max(0, min(100, volume))
        if auto_save:
            self.save()

    def set_current_file(self, file_path: Optional[str], auto_save: bool = True):
        """Set the current file path"""
        self.config['current_file'] = file_path

        # Add to recent files
        if file_path:
            self.add_recent_file(file_path, auto_save=False)

        if auto_save:
            self.save()

    def set_current_folder(self, folder_path: Optional[str], auto_save: bool = True):
        """Set the current folder path"""
        self.config['current_folder'] = folder_path

        # Add to recent folders
        if folder_path:
            self.add_recent_folder(folder_path, auto_save=False)

        if auto_save:
            self.save()

    def set_current_playlist_path(self, playlist_path: Optional[str], auto_save: bool = True):
        """Set the current playlist files"""
        self.config['current_playlist_path'] = playlist_path

        # Add to recent playlists
        if playlist_path:
            self.add_recent_playlist(playlist_path, auto_save=False)

        if auto_save:
            self.save()

    def set_current_playlist_index(self, index: int, auto_save: bool = True):
        """Set the current playlist index"""
        self.config['current_playlist_index'] = index
        if auto_save:
            self.save()

    def set_last_position(self, position: float, auto_save: bool = True):
        """Set the last playback position"""
        self.config['last_position'] = position
        if auto_save:
            self.save()

    def set_shuffle_mode(self, enabled: bool, auto_save: bool = True):
        """Set shuffle mode state"""
        self.config['shuffle_mode'] = enabled
        if auto_save:
            self.save()

    def set_window_position(self, window_name: str, x: int, y: int,
                           width: int, height: int, auto_save: bool = True):
        """Set window position and size"""
        if 'window_positions' not in self.config:
            self.config['window_positions'] = {}

        self.config['window_positions'][window_name] = {
            'x': x,
            'y': y,
            'width': width,
            'height': height
        }

        if auto_save:
            self.save()

    def set_default_load_folder(self, folder_path: str, auto_save: bool = True):
        """Set default folder for loading files"""
        self.config['default_load_folder'] = folder_path
        if auto_save:
            self.save()

    def set_playlist_directory(self, directory: str, auto_save: bool = True):
        """Set playlist directory"""
        self.config['playlist_directory'] = directory
        if auto_save:
            self.save()

    def set_default_playlists(self, playlists: List[str], auto_save: bool = True):
        """Set list of default playlists"""
        self.config['default_playlists'] = playlists
        if auto_save:
            self.save()

    def set_autoplay_on_launch(self, enabled, auto_save=False):
        """Set autoplay on launch setting"""
        self.config['autoplay_on_launch'] = enabled
        if auto_save:
            self.save_config()

    # Recent items management
    def add_recent_file(self, file_path: str, max_count: int = 10, auto_save: bool = True):
        """Add a file to recent files list"""
        recent = self.config.get('recent_files', [])

        # Remove if already exists
        if file_path in recent:
            recent.remove(file_path)

        # Add to front
        recent.insert(0, file_path)

        # Trim to max count
        self.config['recent_files'] = recent[:max_count]

        if auto_save:
            self.save()

    def add_recent_folder(self, folder_path: str, max_count: int = 10, auto_save: bool = True):
        """Add a folder to recent folders list"""
        recent = self.config.get('recent_folders', [])

        # Remove if already exists
        if folder_path in recent:
            recent.remove(folder_path)

        # Add to front
        recent.insert(0, folder_path)

        # Trim to max count
        self.config['recent_folders'] = recent[:max_count]

        if auto_save:
            self.save()

    def add_recent_playlist(self, playlist_path: str, max_count: int = 10, auto_save: bool = True):
        """Add a playlist to recent playlists list"""
        recent = self.config.get('recent_playlists', [])

        # Remove if already exists
        if playlist_path in recent:
            recent.remove(playlist_path)

        # Add to front
        recent.insert(0, playlist_path)

        # Trim to max count
        self.config['recent_playlists'] = recent[:max_count]

        if auto_save:
            self.save()

    # Batch updates
    def update_playback_state(self, file_path: Optional[str] = None,
                             position: float = None, volume: int = None,
                             auto_save: bool = True):
        """
        Update multiple playback state values at once

        Args:
            file_path: Current file path
            position: Current playback position
            volume: Current volume level
            auto_save: Whether to save immediately
        """
        if file_path is not None:
            self.set_current_file(file_path, auto_save=False)

        if position is not None:
            self.set_last_position(position, auto_save=False)

        if volume is not None:
            self.set_volume(volume, auto_save=False)

        if auto_save:
            self.save()

    def update_playlist_state(self, playlist_path: str = None,
                              index: int = None, folder: str = None,
                              auto_save: bool = True):
        """
        Update multiple playlist state values at once

        Args:
            playlist_path: Current playlist file path
            index: Current playlist index
            folder: Current folder path
            auto_save: Whether to save immediately
        """
        if playlist_path is not None:
            self.set_current_playlist_path(playlist_path, auto_save=False)

        if index is not None:
            self.set_current_playlist_index(index, auto_save=False)

        if folder is not None:
            self.set_current_folder(folder, auto_save=False)

        if auto_save:
            self.save()

    # Profile management
    def switch_profile(self, profile_name: str) -> bool:
        """
        Switch to a different profile

        Args:
            profile_name: Name of the profile to switch to

        Returns:
            True if switched successfully, False otherwise
        """
        old_profile = self.profile_name
        self.profile_name = profile_name
        self.config_file = os.path.join(self.profiles_dir, f'{profile_name}.json')

        # Reset to defaults
        self.config = self._get_default_config()

        # Try to load the profile
        if self.load():
            self.logger.info(f'Switched from profile "{old_profile}" to "{profile_name}"')
            return True
        else:
            self.logger.info(f'Created new profile: {profile_name}')
            self.save()  # Save the default config for the new profile
            return True

    def list_profiles(self) -> List[str]:
        """
        List all available profiles

        Returns:
            List of profile names
        """
        try:
            if not os.path.exists(self.profiles_dir):
                return []

            profiles = []
            for file in os.listdir(self.profiles_dir):
                if file.endswith('.json'):
                    profiles.append(file[:-5])  # Remove .json extension

            return sorted(profiles)

        except Exception as e:
            self.logger.error(f'Failed to list profiles: {e}')
            return []

    def delete_profile(self, profile_name: str) -> bool:
        """
        Delete a profile

        Args:
            profile_name: Name of the profile to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        if profile_name == self.profile_name:
            self.logger.warning(f'Cannot delete current profile: {profile_name}')
            return False

        try:
            profile_file = os.path.join(self.profiles_dir, f'{profile_name}.json')
            if os.path.exists(profile_file):
                os.remove(profile_file)
                self.logger.info(f'Deleted profile: {profile_name}')
                return True
            else:
                self.logger.warning(f'Profile not found: {profile_name}')
                return False

        except Exception as e:
            self.logger.error(f'Failed to delete profile: {e}')
            return False
