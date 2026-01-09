"""
Custom exceptions for Spotify Release Tracker.

Provides specific exception types for different error scenarios.
"""


class ArtistTrackerException(Exception):
    """Base exception for artist tracker."""
    pass


class DatabaseError(ArtistTrackerException):
    """Database operation failed."""
    pass


class SpotifyAPIError(ArtistTrackerException):
    """Spotify API error."""

    def __init__(self, message: str, status_code: int = None):
        """
        Initialize SpotifyAPIError.

        Args:
            message: Error message
            status_code: HTTP status code if available
        """
        self.status_code = status_code
        super().__init__(message)


class RateLimitError(SpotifyAPIError):
    """Spotify API rate limit exceeded."""

    def __init__(self, message: str = "Spotify API rate limit exceeded", retry_after: int = None):
        """
        Initialize RateLimitError.

        Args:
            message: Error message
            retry_after: Seconds to wait before retrying
        """
        self.retry_after = retry_after
        super().__init__(message, status_code=429)


class InvalidInputError(ArtistTrackerException):
    """Invalid user input."""
    pass


class ArtistNotFoundError(ArtistTrackerException):
    """Artist not found on Spotify."""

    def __init__(self, artist_input: str):
        """
        Initialize ArtistNotFoundError.

        Args:
            artist_input: The artist name or ID that was not found
        """
        self.artist_input = artist_input
        super().__init__(f"Artist not found: {artist_input}")


class PlaylistNotFoundError(ArtistTrackerException):
    """Playlist not found or not accessible."""

    def __init__(self, playlist_id: str):
        """
        Initialize PlaylistNotFoundError.

        Args:
            playlist_id: The playlist ID that was not found
        """
        self.playlist_id = playlist_id
        super().__init__(f"Playlist not found or not accessible: {playlist_id}")


class ValidationError(InvalidInputError):
    """Input validation failed."""

    def __init__(self, field: str, value: str, reason: str):
        """
        Initialize ValidationError.

        Args:
            field: Name of the field that failed validation
            value: The invalid value
            reason: Reason for validation failure
        """
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"Validation failed for {field}='{value}': {reason}")
