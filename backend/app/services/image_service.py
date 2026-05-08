import asyncio
import base64
import io
import threading
from typing import Optional

import ollama
from loguru import logger

from config.settings import settings


class ImageAnalyzer:
    """Image analysis via llava (Ollama vision model) with pytesseract OCR fallback."""

    def __init__(self):
        self._tesseract_available: Optional[bool] = None
        self._llava_available: Optional[bool] = None

    def _check_tesseract(self) -> bool:
        if self._tesseract_available is None:
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
                self._tesseract_available = True
                logger.info("Tesseract OCR available")
            except Exception:
                self._tesseract_available = False
                logger.info("Tesseract OCR not available (install tesseract + pytesseract)")
        return self._tesseract_available

    def _check_llava(self) -> bool:
        if self._llava_available is None:
            try:
                client = ollama.Client(host=settings.ollama_base_url)
                response = client.list()
                models_list = getattr(response, "models", []) or []
                model_names = []
                for m in models_list:
                    name = getattr(m, "model", None) or getattr(m, "name", "") or ""
                    model_names.append(name.lower())
                self._llava_available = any("llava" in n for n in model_names)
                if self._llava_available:
                    logger.info("llava vision model available")
                else:
                    logger.info("llava not available — run: ollama pull llava")
            except Exception:
                self._llava_available = False
        return self._llava_available

    async def analyze(self, image_bytes: bytes, user_query: str = "") -> dict:
        description = ""
        ocr_text = ""

        if self._check_llava():
            description = await self._analyze_with_llava(image_bytes, user_query)

        if self._check_tesseract():
            ocr_text = await asyncio.to_thread(self._run_ocr, image_bytes)

        parts = []
        if description:
            parts.append(f"Image Analysis:\n{description}")
        if ocr_text.strip():
            parts.append(f"Extracted Text (OCR):\n{ocr_text.strip()}")

        if not parts:
            combined = (
                "Could not analyze image. "
                "Install Tesseract (https://github.com/UB-Mannheim/tesseract/wiki) "
                "or run: ollama pull llava"
            )
        else:
            combined = "\n\n".join(parts)

        return {
            "description": description,
            "ocr_text": ocr_text,
            "combined": combined,
            "llava_used": bool(description),
            "ocr_used": bool(ocr_text.strip()),
        }

    async def _analyze_with_llava(self, image_bytes: bytes, user_query: str) -> str:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        image_b64 = base64.b64encode(image_bytes).decode()

        prompt = (
            "Analyze this image in detail. Describe what you see, "
            "extract any visible text, identify key information, charts, or data."
        )
        if user_query:
            prompt += f" The user wants to know: {user_query}"

        def run():
            try:
                client = ollama.Client(host=settings.ollama_base_url)
                response = client.chat(
                    model="llava",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        }
                    ],
                )
                loop.call_soon_threadsafe(
                    queue.put_nowait, response.message.content
                )
            except Exception as e:
                logger.debug(f"llava analysis failed: {e}")
                loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            result = await asyncio.wait_for(queue.get(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("llava analysis timed out after 30s")
            result = None
        return result or ""

    def _run_ocr(self, image_bytes: bytes) -> str:
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img)
        except Exception as e:
            logger.debug(f"OCR failed: {e}")
            return ""


image_analyzer = ImageAnalyzer()
