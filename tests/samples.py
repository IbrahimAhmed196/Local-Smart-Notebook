import io
import zipfile


def make_zip(marker: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(marker, "<x/>")
    return buf.getvalue()


# name -> (content, content type sent by the client)
SAMPLES = {
    "report.pdf": (b"%PDF-1.4\n%fake pdf body\n", "application/pdf"),
    "notes.docx": (make_zip("word/document.xml"), "application/octet-stream"),
    "sheet.xlsx": (make_zip("xl/workbook.xml"), "application/octet-stream"),
    "data.csv": (b"a,b\n1,2\n3,4\n", "text/csv"),
    "readme.txt": (b"hello world\n", "text/plain"),
    "ملف عربي.txt": ("مرحبا".encode("utf-8"), "text/plain"),
}
