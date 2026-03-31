"""LLM-based security analysis module for IRIS."""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
from openai import OpenAI

from src.config import IntelligenceConfig, get_prompt
from src.memory.event_store import SecurityEvent
from src.vision.camera import encode_frame_base64

logger = logging.getLogger(__name__)


class SecurityAnalyzer:
    """Analyzes frames using GPT-4o Vision for security assessment."""

    def __init__(self, config: IntelligenceConfig, api_key: str):
        """
        Initialize security analyzer.

        Args:
            config: Intelligence configuration
            api_key: OpenAI API key
        """
        self.config = config
        self.client = OpenAI(api_key=api_key)

        # Load system prompt
        try:
            self.system_prompt = get_prompt("security")
        except FileNotFoundError:
            logger.warning("Security prompt not found, using default")
            self.system_prompt = self._get_default_prompt()

        logger.info(f"Security analyzer initialized with model: {config.model}")

    def analyze_frame(
        self, frame: np.ndarray, recent_events: Optional[List[SecurityEvent]] = None
    ) -> Optional[SecurityEvent]:
        """
        Analyze a frame for security concerns.

        Args:
            frame: Camera frame (BGR format)
            recent_events: Recent events for context

        Returns:
            SecurityEvent or None if analysis fails
        """
        try:
            # Encode frame as base64
            frame_b64 = encode_frame_base64(frame, quality=85)

            # Build context from recent events
            context = self._build_context(recent_events)

            # Format prompt with context
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_prompt = self.system_prompt.format(
                timestamp=current_time, recent_events=context
            )

            # Call GPT-4o Vision API
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{frame_b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )

            # Extract response
            content = response.choices[0].message.content.strip()

            # Parse JSON response
            analysis = self._parse_response(content)

            if analysis is None:
                logger.error("Failed to parse LLM response")
                return None

            # Create SecurityEvent
            event = SecurityEvent(
                scene_description=analysis["scene"],
                people_count=analysis["people_count"],
                activity=analysis["activity"],
                threat_level=analysis["threat_level"],
                reasoning=analysis["reasoning"],
                metadata={
                    "model": self.config.model,
                    "temperature": self.config.temperature,
                    "tokens_used": response.usage.total_tokens,
                },
            )

            logger.info(
                f"Analysis complete: {event.threat_level} threat - {event.scene_description}"
            )

            return event

        except Exception as e:
            logger.error(f"Error during frame analysis: {e}", exc_info=True)
            return None

    def _build_context(self, recent_events: Optional[List[SecurityEvent]]) -> str:
        """
        Build context string from recent events.

        Args:
            recent_events: List of recent SecurityEvents

        Returns:
            Formatted context string
        """
        if not recent_events or not self.config.include_recent_context:
            return "No recent events."

        # Limit to context window
        events = recent_events[: self.config.context_window]

        context_lines = []
        for event in events:
            time_str = event.timestamp.strftime("%H:%M:%S")
            context_lines.append(
                f"[{time_str}] {event.threat_level.upper()}: {event.scene_description}"
            )

        return "\n".join(context_lines)

    def _parse_response(self, content: str) -> Optional[Dict]:
        """
        Parse LLM response into structured format.

        Args:
            content: Raw LLM response

        Returns:
            Parsed dictionary or None if invalid
        """
        try:
            # Try to extract JSON from response
            # Sometimes LLM adds markdown code blocks
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            # Parse JSON
            data = json.loads(content)

            # Validate required fields
            required_fields = [
                "scene",
                "people_count",
                "activity",
                "threat_level",
                "reasoning",
            ]

            for field in required_fields:
                if field not in data:
                    logger.error(f"Missing required field: {field}")
                    return None

            # Validate values
            valid_activities = ["normal", "suspicious", "alert"]
            valid_threats = ["none", "low", "medium", "high"]

            if data["activity"] not in valid_activities:
                logger.warning(
                    f"Invalid activity: {data['activity']}, defaulting to 'normal'"
                )
                data["activity"] = "normal"

            if data["threat_level"] not in valid_threats:
                logger.warning(
                    f"Invalid threat level: {data['threat_level']}, defaulting to 'none'"
                )
                data["threat_level"] = "none"

            # Ensure people_count is int
            data["people_count"] = int(data["people_count"])

            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}\nContent: {content}")
            return None
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return None

    def _get_default_prompt(self) -> str:
        """Get default security prompt if file not found."""
        return """You are IRIS, a security monitoring AI.

Analyze this frame and respond with JSON:
{
  "scene": "Brief description",
  "people_count": <number>,
  "activity": "normal|suspicious|alert",
  "threat_level": "none|low|medium|high",
  "reasoning": "Explanation"
}

Time: {timestamp}
Recent: {recent_events}"""
