"""PDF text extraction utility using pdfplumber."""

import io

import pdfplumber
from fastapi import UploadFile


def extract_text_from_pdf(upload_file: UploadFile) -> str:
    """
    Extract text from an uploaded PDF file.

    Args:
        upload_file: FastAPI UploadFile object

    Returns:
        Extracted text as string, or empty string if extraction fails
    """
    try:
        # Read the file content
        content = upload_file.file.read()

        # Reset file pointer for potential reuse
        upload_file.file.seek(0)

        # Open PDF with pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            return text.strip()

    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""