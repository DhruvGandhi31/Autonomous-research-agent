from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from loguru import logger

from services.image_service import image_analyzer
from services.document_extractor import document_extractor

router = APIRouter()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}
ALLOWED_DOC_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    query: str = Form(default=""),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            400,
            f"Unsupported image type: {file.content_type}. Allowed: JPEG, PNG, GIF, WEBP, BMP",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large. Maximum size is 20MB.")

    logger.info(f"Analyzing image: {file.filename} ({len(content)} bytes)")
    result = await image_analyzer.analyze(content, user_query=query)

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "extracted_text": result["combined"],
        "description": result["description"],
        "ocr_text": result["ocr_text"],
        "llava_used": result["llava_used"],
        "ocr_used": result["ocr_used"],
        "file_type": "image",
    }


@router.post("/document")
async def upload_document(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    filename = file.filename or ""

    is_allowed = (
        content_type in ALLOWED_DOC_TYPES
        or filename.endswith(".pdf")
        or filename.endswith(".docx")
        or filename.endswith(".doc")
        or filename.endswith(".txt")
    )
    if not is_allowed:
        raise HTTPException(
            400,
            f"Unsupported document type. Allowed: PDF, DOCX, TXT",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large. Maximum size is 20MB.")

    logger.info(f"Extracting document: {filename} ({len(content)} bytes)")
    result = document_extractor.extract(content, filename)

    if result.get("error"):
        raise HTTPException(500, f"Failed to extract document: {result['error']}")

    text = result["text"]
    # Truncate very long documents to stay within LLM context
    preview = text[:500] + ("..." if len(text) > 500 else "")

    return {
        "filename": filename,
        "content_type": content_type,
        "size": len(content),
        "extracted_text": text[:50_000],  # cap at 50k chars for LLM context
        "description": f"Document '{filename}' — {result['pages']} pages/paragraphs extracted",
        "preview": preview,
        "char_count": len(text),
        "method": result.get("method", "unknown"),
        "file_type": "document",
    }
