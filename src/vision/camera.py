"""Camera capture module for IRIS Security Agent."""

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from src.config import CameraConfig

logger = logging.getLogger(__name__)


class Camera:
    """Handles camera capture and frame management."""

    def __init__(self, config: CameraConfig):
        """
        Initialize camera.

        Args:
            config: Camera configuration
        """
        self.config = config
        self.capture: Optional[cv2.VideoCapture] = None
        self.is_open = False

    def open(self) -> bool:
        """
        Open camera connection.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.capture = cv2.VideoCapture(self.config.device_id)

            if not self.capture.isOpened():
                logger.error(f"Failed to open camera {self.config.device_id}")
                return False

            # Set resolution
            width, height = self.config.resolution
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.capture.set(cv2.CAP_PROP_FPS, self.config.fps)

            # Warmup - read initial frames to stabilize camera
            logger.info(f"Warming up camera ({self.config.warmup_frames} frames)...")
            for _ in range(self.config.warmup_frames):
                self.capture.read()

            self.is_open = True
            logger.info(
                f"Camera opened successfully: {width}x{height} @ {self.config.fps}fps"
            )
            return True

        except Exception as e:
            logger.error(f"Error opening camera: {e}")
            return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a single frame from camera.

        Returns:
            Tuple of (success, frame)
        """
        if not self.is_open or self.capture is None:
            return False, None

        try:
            ret, frame = self.capture.read()

            if not ret or frame is None:
                logger.warning("Failed to read frame from camera")
                return False, None

            # Flip horizontally if configured (useful for selfie cameras)
            if self.config.flip_horizontal:
                frame = cv2.flip(frame, 1)

            return True, frame

        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            return False, None

    def get_frame_size(self) -> Tuple[int, int]:
        """
        Get current frame dimensions.

        Returns:
            Tuple of (width, height)
        """
        if not self.is_open or self.capture is None:
            return tuple(self.config.resolution)

        width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return width, height

    def close(self):
        """Release camera resources."""
        if self.capture is not None:
            self.capture.release()
            self.is_open = False
            logger.info("Camera closed")

    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Destructor to ensure camera is released."""
        self.close()


def save_frame(frame: np.ndarray, path: str, quality: int = 85) -> bool:
    """
    Save a frame to disk as JPEG.

    Args:
        frame: Frame to save
        path: Output file path
        quality: JPEG quality (0-100)

    Returns:
        True if successful, False otherwise
    """
    try:
        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return True
    except Exception as e:
        logger.error(f"Error saving frame to {path}: {e}")
        return False


def encode_frame_base64(frame: np.ndarray, quality: int = 85) -> str:
    """
    Encode frame as base64 JPEG string for API transmission.

    Args:
        frame: Frame to encode
        quality: JPEG quality (0-100)

    Returns:
        Base64 encoded string
    """
    import base64

    # Encode as JPEG
    success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])

    if not success:
        raise ValueError("Failed to encode frame as JPEG")

    # Convert to base64
    jpg_as_text = base64.b64encode(buffer).decode("utf-8")
    return jpg_as_text
