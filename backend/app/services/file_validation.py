"""File type + content validation (extension whitelist and signature sniffing)."""
import zipfile
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import InvalidFileError, UnsupportedFileTypeError

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def get_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        allowed = ", ".join(e.lstrip(".") for e in settings.allowed_extensions)
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext or 'none'}'. Allowed types: {allowed}."
        )
    return ext


def validate_content(path: Path, ext: str) -> None:
    """Check that the bytes really match the claimed extension."""
    with open(path, "rb") as f:
        head = f.read(8192)

    if ext == ".pdf":
        if not head.startswith(b"%PDF-"):
            raise InvalidFileError("File content is not a valid PDF.")
    elif ext in (".docx", ".xlsx"):
        marker = "word/document.xml" if ext == ".docx" else "xl/workbook.xml"
        try:
            with zipfile.ZipFile(path) as z:
                ok = marker in z.namelist()
        except zipfile.BadZipFile:
            ok = False
        if not ok:
            raise InvalidFileError(f"File content is not a valid {ext.lstrip('.').upper()} file.")
    else:  # .txt / .csv
        if head.startswith((b"\xff\xfe", b"\xfe\xff")):     # UTF-16 BOM
            return
        if b"\x00" in head:
            raise InvalidFileError(
                f"File content does not look like a valid {ext.lstrip('.').upper()} text file."
            )
