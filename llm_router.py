import os
import time
import logging

from google import genai
from google.genai import types


logger = logging.getLogger("rag_api")


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing")


gemini_client = genai.Client(
    api_key=API_KEY
)


# Primary model + fallback model
MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]


MAX_RETRIES_PER_MODEL = 3

BACKOFF_SECONDS = [
    1,
    2,
    4,
]


# ============================================================
# ERROR HANDLING
# ============================================================

def is_retryable_error(error: Exception) -> bool:

    error_text = str(error).upper()

    retryable_errors = [
        "503",
        "UNAVAILABLE",
        "429",
        "RESOURCE_EXHAUSTED",
        "500",
        "502",
        "504",
        "INTERNAL",
        "DEADLINE",
        "TIMEOUT",
    ]

    return any(
        error_code in error_text
        for error_code in retryable_errors
    )


# ============================================================
# SINGLE MODEL GENERATION
# ============================================================

def _generate_with_model(
    prompt: str,
    model: str,
):

    logger.info(
        "Starting Gemini generation | model=%s",
        model,
    )

    stream = (
        gemini_client.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1024,
                thinking_config=types.ThinkingConfig(
                    thinking_level="low"
                ),
            ),
        )
    )

    got_text = False

    for chunk in stream:

        if chunk.text:

            got_text = True

            yield chunk.text


    if not got_text:

        raise RuntimeError(
            f"Gemini model {model} returned an empty response."
        )


# ============================================================
# MAIN STREAMING FUNCTION
# ============================================================

def generate_answer_stream(prompt: str):

    last_error = None


    # ========================================================
    # TRY PRIMARY + FALLBACK MODELS
    # ========================================================

    for model in MODELS:

        logger.info(
            "Trying Gemini model: %s",
            model,
        )


        # ====================================================
        # RETRIES
        # ====================================================

        for attempt in range(
            MAX_RETRIES_PER_MODEL
        ):

            try:

                logger.info(
                    "Gemini request | model=%s | attempt=%d/%d",
                    model,
                    attempt + 1,
                    MAX_RETRIES_PER_MODEL,
                )


                # --------------------------------------------
                # STREAM RESPONSE
                # --------------------------------------------

                for text in _generate_with_model(
                    prompt,
                    model,
                ):

                    yield text


                # --------------------------------------------
                # SUCCESS
                # --------------------------------------------

                logger.info(
                    "Gemini generation successful | model=%s",
                    model,
                )

                return


            except Exception as error:

                last_error = error


                logger.exception(
                    "Gemini generation failed | "
                    "model=%s | attempt=%d/%d",
                    model,
                    attempt + 1,
                    MAX_RETRIES_PER_MODEL,
                )


                # --------------------------------------------
                # NON-RETRYABLE ERROR
                # --------------------------------------------

                if not is_retryable_error(error):

                    logger.error(
                        "Non-retryable Gemini error."
                    )

                    break


                # --------------------------------------------
                # RETRY
                # --------------------------------------------

                if attempt < (
                    MAX_RETRIES_PER_MODEL - 1
                ):

                    delay = BACKOFF_SECONDS[
                        attempt
                    ]

                    logger.warning(
                        "Temporary Gemini error. "
                        "Retrying in %s seconds...",
                        delay,
                    )

                    time.sleep(delay)

                else:

                    logger.warning(
                        "Model %s failed after %d attempts. "
                        "Trying fallback model.",
                        model,
                        MAX_RETRIES_PER_MODEL,
                    )


    # ========================================================
    # ALL MODELS FAILED
    # ========================================================

    logger.error(
        "All Gemini models failed. Last error: %s",
        last_error,
    )


    yield (
        "\n\n"
        "Sorry, the AI generation service is temporarily "
        "unavailable. Please try again in a moment."
    )
