import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger("rag_api")

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def generate_answer_stream(prompt: str):
    """Gemini se streaming answer generate karta hai."""
    try:
        stream = gemini_client.models.generate_content_stream(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1024,
                temperature=0.3,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            )
        )
        got_any_text = False
        for chunk in stream:
            if chunk.text:
                got_any_text = True
                yield chunk.text
        if not got_any_text:
            yield "\n[No response was generated. Please try again.]"
    except Exception as e:
        logger.error(f"Generation error: {e}")
        yield "\n[The answer-generation service is temporarily unavailable. Please try again.]"
