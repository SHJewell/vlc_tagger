"""
App Registry - Central registry for application components.
No project imports allowed in this file to avoid circular imports.
"""
import logging

logger = logging.getLogger(__name__)

_components: dict = {}


def register(name: str, component) -> None:
    """Register a component by name, replacing any existing instance."""
    if name in _components:
        logger.debug(f'Replacing existing component: {name}')
    _components[name] = component
    logger.debug(f'Registered component: {name}')


def unregister(name: str) -> None:
    """Remove a component from the registry."""
    if name in _components:
        del _components[name]
        logger.debug(f'Unregistered component: {name}')


def get(name: str, default=None):
    """Retrieve a registered component by name."""
    return _components.get(name, default)
