"""
LLM Client wrapper for Anthropic Claude API.

Responsibilities:
1. Wrap API calls with retry logic
2. Enforce JSON-only output for structured queries
3. Parse JSON safely (handle malformed responses)
4. Raise specific exceptions on failure (not silent crashes)

Input: Text prompt + optional context
Output: Either raw text or parsed JSON

Failure handling:
- API timeouts → raise LLMClientException (module can fall back to unable_to_verify)
- Malformed JSON → raise JSONParseException
- Rate limiting → automatic retry with backoff
"""

import logging
import json
import re
from typing import Any, Dict, Optional
import time

import anthropic
from anthropic import APIError, APITimeoutError, RateLimitError

from core.config import settings

logger = logging.getLogger(__name__)


class LLMClientException(Exception):
    """Base exception for LLM client errors."""
    pass


class JSONParseException(LLMClientException):
    """Exception raised when JSON parsing fails."""
    pass


class LLMClient:
    """
    Wrapper around Anthropic Claude API.
    """
    
    # Configuration
    MODEL = "claude-3-5-sonnet-20241022"
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2
    TIMEOUT_SECONDS = 30
    MAX_TOKENS = 1024
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize LLM client.
        
        Args:
            api_key: Anthropic API key. If not provided, reads from ANTHROPIC_API_KEY env var.
        """
        api_key = api_key or settings.ANTHROPIC_API_KEY
        if not api_key:
            raise LLMClientException("ANTHROPIC_API_KEY not set")
        
        self.client = anthropic.Anthropic(api_key=api_key)
        logger.info(f"[LLMClient] Initialized with model: {self.MODEL}")
    
    def query_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,  # Low temp for consistency
    ) -> str:
        """
        Query Claude and return raw text response.
        
        Args:
            prompt: User message
            system_prompt: System message (instructions)
            temperature: Sampling temperature (0.0-1.0)
            
        Returns:
            Response text
            
        Raises:
            LLMClientException: If call fails after retries
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.MODEL,
                    max_tokens=self.MAX_TOKENS,
                    temperature=temperature,
                    system=system_prompt or "You are a helpful assistant.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    timeout=self.TIMEOUT_SECONDS,
                )
                
                return response.content[0].text
            
            except RateLimitError as e:
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(f"[LLMClient] Rate limited, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise LLMClientException(f"Rate limited after {self.MAX_RETRIES} attempts: {str(e)}")
            
            except APITimeoutError as e:
                raise LLMClientException(f"API timeout: {str(e)}")
            
            except APIError as e:
                raise LLMClientException(f"API error: {str(e)}")
        
        raise LLMClientException("Failed to get response from LLM")
    
    def query_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Query Claude and parse response as JSON.
        
        Handles malformed responses:
        - Strips markdown code fences (```json ... ```)
        - Removes leading/trailing text before JSON
        - Attempts to recover from common formatting errors
        
        Args:
            prompt: User message
            system_prompt: System message (should instruct JSON output)
            temperature: Sampling temperature
            
        Returns:
            Parsed JSON as dict
            
        Raises:
            JSONParseException: If JSON parsing fails
            LLMClientException: If API call fails
        """
        if not system_prompt:
            system_prompt = (
                "You are a JSON-only assistant. "
                "Respond ONLY with valid JSON, no markdown, no extra text. "
                "Never wrap in markdown code fences."
            )
        
        response_text = self.query_text(prompt, system_prompt, temperature)
        
        # Parse JSON with error recovery
        return self._parse_json_response(response_text)
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse JSON from response, handling common formatting issues.
        
        Args:
            response_text: Raw response from LLM
            
        Returns:
            Parsed JSON
            
        Raises:
            JSONParseException: If parsing fails
        """
        # Try direct parse first
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass
        
        # Strip markdown code fences
        text = response_text
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        
        # Try again
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from leading/trailing text
        # Look for { ... } pattern
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        # Give up
        logger.error(f"[LLMClient] Failed to parse JSON response: {response_text[:200]}")
        raise JSONParseException(
            f"Could not parse JSON from response. Got: {response_text[:100]}"
        )


# Singleton instance
try:
    llm_client = LLMClient()
except LLMClientException as e:
    logger.error(f"[LLMClient] Failed to initialize: {str(e)}")
    llm_client = None
