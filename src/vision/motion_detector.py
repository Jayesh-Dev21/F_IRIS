"""Motion detection module for IRIS Security Agent."""

import logging
from typing import Optional, Tuple

import cv2
import numpy as np
from imutils import contours as imutils_contours

from src.config import MonitoringConfig

logger = logging.getLogger(__name__)


class MotionDetector:
    """Detects motion in video frames using background subtraction."""

    def __init__(self, config: MonitoringConfig):
        """
        Initialize motion detector.

        Args:
            config: Monitoring configuration
        """
        self.config = config

        # Background subtractor (MOG2 is good for varying lighting)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=self.config.motion_threshold, detectShadows=True
        )

        # Kernel for morphological operations
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        self.is_initialized = False
        self.frame_count = 0

    def detect(self, frame: np.ndarray) -> Tuple[bool, int, Optional[np.ndarray]]:
        """
        Detect motion in frame.

        Args:
            frame: Input frame (BGR format)

        Returns:
            Tuple of (motion_detected, motion_area, annotated_frame)
        """
        self.frame_count += 1

        # Apply background subtraction
        fg_mask = self.bg_subtractor.apply(frame)

        # Remove shadows (value 127 in MOG2)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Morphological operations to reduce noise
        fg_mask = cv2.erode(fg_mask, self.kernel, iterations=1)
        fg_mask = cv2.dilate(fg_mask, self.kernel, iterations=2)

        # Find contours
        contours_list, _ = cv2.findContours(
            fg_mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Calculate total motion area
        total_motion_area = 0
        motion_detected = False
        annotated_frame = frame.copy()

        for contour in contours_list:
            area = cv2.contourArea(contour)

            if area < self.config.min_motion_area:
                continue

            total_motion_area += area
            motion_detected = True

            # Draw bounding box on frame
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        # Add motion area text
        if motion_detected:
            cv2.putText(
                annotated_frame,
                f"Motion: {total_motion_area} px",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

        # First few frames are used to build background model
        if self.frame_count < 30:
            self.is_initialized = False
            return False, 0, annotated_frame

        self.is_initialized = True

        return motion_detected, total_motion_area, annotated_frame

    def reset(self):
        """Reset the background model."""
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=self.config.motion_threshold, detectShadows=True
        )
        self.frame_count = 0
        self.is_initialized = False
        logger.info("Motion detector reset")


class FrameComparator:
    """Simple frame comparison for detecting changes."""

    def __init__(self, threshold: int = 25):
        """
        Initialize frame comparator.

        Args:
            threshold: Difference threshold (0-255)
        """
        self.threshold = threshold
        self.previous_frame: Optional[np.ndarray] = None

    def detect_change(
        self, frame: np.ndarray, min_changed_pixels: int = 1000
    ) -> Tuple[bool, float]:
        """
        Detect changes between current and previous frame.

        Args:
            frame: Current frame (BGR)
            min_changed_pixels: Minimum number of changed pixels to trigger

        Returns:
            Tuple of (change_detected, change_percentage)
        """
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        # First frame - just store it
        if self.previous_frame is None:
            self.previous_frame = gray
            return False, 0.0

        # Compute difference
        frame_delta = cv2.absdiff(self.previous_frame, gray)
        thresh = cv2.threshold(frame_delta, self.threshold, 255, cv2.THRESH_BINARY)[1]

        # Count changed pixels
        changed_pixels = cv2.countNonZero(thresh)
        total_pixels = frame.shape[0] * frame.shape[1]
        change_percentage = (changed_pixels / total_pixels) * 100

        # Update previous frame
        self.previous_frame = gray

        change_detected = changed_pixels >= min_changed_pixels

        return change_detected, change_percentage

    def reset(self):
        """Reset the comparator."""
        self.previous_frame = None
