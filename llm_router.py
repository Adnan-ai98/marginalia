import os
import logging

from google import genai
from google.genai import types

logger = logging.getLogger("rag_api")

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing")

gemini_client = genai.Client(api_key=API_KEY)


def generate_answer_stream(prompt: str):
    """Generate a grounded answer from Gemini with streaming."""

    try:
        logger.info("Starting Gemini generation...")

        stream = gemini_client.models.generate_content_stream(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1024,
                thinking_config=types.ThinkingConfig(
                    thinking_level="low"
                ),
            ),
        )

        got_any_text = False

        for chunk in stream:
            if chunk.text:
                got_any_text = True
                yield chunk.text

        if not got_any_text:
            logger.error("Gemini returned no text.")
            yield "\n[Gemini returned no answer.]"

    except Exception as e:
        logger.exception("Gemini generation failed")

        # Make the real failure visible in Railway logs
        error_message = str(e)

        yield (
            "\n[Generation error: "
            + error_message
            + "]"
        )
