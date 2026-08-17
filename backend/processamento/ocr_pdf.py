"""Extração de páginas com fallback OCR local e metadados de proveniência."""

from dataclasses import dataclass
import os
import re

import fitz


DEFAULT_OCR_LANGUAGES = "por+eng"
DEFAULT_OCR_DPI = 300
DEFAULT_MIN_NATIVE_CHARACTERS = 40


def _read_bool(name, default):
    value = os.getenv(name)
    if value is None or not value.strip():
        return bool(default)
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "sim"}:
        return True
    if normalized in {"0", "false", "no", "off", "nao", "não"}:
        return False
    raise RuntimeError(f"{name} deve ser verdadeiro ou falso.")


def _read_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name} deve ser um número inteiro.") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} deve estar entre {minimum} e {maximum}.")
    return value


@dataclass(frozen=True)
class PdfOcrConfig:
    enabled: bool = True
    languages: str = DEFAULT_OCR_LANGUAGES
    dpi: int = DEFAULT_OCR_DPI
    min_native_characters: int = DEFAULT_MIN_NATIVE_CHARACTERS
    tessdata: str | None = None

    def metadata(self):
        return {
            "enabled": self.enabled,
            "languages": self.languages,
            "dpi": self.dpi,
            "min_native_characters": self.min_native_characters,
        }


def get_pdf_ocr_config():
    languages = os.getenv("PDF_OCR_LANGUAGES", DEFAULT_OCR_LANGUAGES).strip()
    if not languages or not re.fullmatch(r"[A-Za-z0-9_+.-]+", languages):
        raise RuntimeError(
            "PDF_OCR_LANGUAGES deve conter códigos Tesseract separados por '+'."
        )
    tessdata = os.getenv("PDF_OCR_TESSDATA") or os.getenv("TESSDATA_PREFIX") or None
    return PdfOcrConfig(
        enabled=_read_bool("PDF_OCR_ENABLED", True),
        languages=languages,
        dpi=_read_int("PDF_OCR_DPI", DEFAULT_OCR_DPI, 72, 600),
        min_native_characters=_read_int(
            "PDF_OCR_MIN_NATIVE_CHARACTERS",
            DEFAULT_MIN_NATIVE_CHARACTERS,
            0,
            2_000,
        ),
        tessdata=tessdata,
    )


def sanitize_pdf_text(text):
    """Remove NUL, preservando acentuação e o conteúdo reconhecido."""
    return str(text or "").replace("\x00", "").strip()


def significant_character_count(text):
    return sum(character.isalnum() for character in str(text or ""))


def extract_pdf_document(path, config=None, document_opener=fitz.open):
    """Extrai texto por página e usa OCR somente quando a camada nativa é insuficiente."""
    config = config or get_pdf_ocr_config()
    pages = []
    warnings = []
    null_characters_removed = 0
    total_pages = 0
    ocr_attempted_pages = 0
    ocr_pages = 0
    ocr_failed_pages = 0

    with document_opener(path) as document:
        total_pages = len(document)
        for page_number, page in enumerate(document, start=1):
            native_raw = page.get_text("text")
            null_characters_removed += str(native_raw or "").count("\x00")
            native_text = sanitize_pdf_text(native_raw)
            native_characters = significant_character_count(native_text)
            final_text = native_text
            extraction_method = "native"
            ocr_attempted = False
            ocr_error = None

            if config.enabled and native_characters < config.min_native_characters:
                ocr_attempted = True
                ocr_attempted_pages += 1
                try:
                    text_page = page.get_textpage_ocr(
                        language=config.languages,
                        dpi=config.dpi,
                        full=True,
                        tessdata=config.tessdata,
                    )
                    ocr_text = sanitize_pdf_text(
                        page.get_text("text", textpage=text_page)
                    )
                    if significant_character_count(ocr_text) > native_characters:
                        final_text = ocr_text
                        extraction_method = "ocr"
                        ocr_pages += 1
                    else:
                        ocr_error = "OCR não acrescentou texto útil à camada nativa."
                except Exception as error:
                    ocr_error = str(error).strip() or error.__class__.__name__

                if ocr_error:
                    ocr_failed_pages += 1
                    warnings.append(
                        {"page_number": page_number, "message": ocr_error[:500]}
                    )
                    extraction_method = "native_low_text" if native_text else "unreadable"
            elif native_characters < config.min_native_characters:
                extraction_method = "native_low_text" if native_text else "unreadable"

            if final_text:
                pages.append(
                    {
                        "page_number": page_number,
                        "text": final_text,
                        "text_extraction_method": extraction_method,
                        "native_character_count": native_characters,
                        "ocr_attempted": ocr_attempted,
                        "ocr_languages": config.languages if extraction_method == "ocr" else None,
                        "ocr_dpi": config.dpi if extraction_method == "ocr" else None,
                    }
                )

    return {
        "pages": pages,
        "total_pages": total_pages,
        "text_pages": len(pages),
        "empty_pages": max(0, total_pages - len(pages)),
        "ocr_attempted_pages": ocr_attempted_pages,
        "ocr_pages": ocr_pages,
        "ocr_failed_pages": ocr_failed_pages,
        "warnings": warnings,
        "null_characters_removed": null_characters_removed,
        "ocr_config": config.metadata(),
    }
