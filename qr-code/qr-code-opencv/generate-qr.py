import fitz  # PyMuPDF
import qrcode
import io
import hashlib


def generate_md5_checksum(txt: str, secret: str) -> str:
    """Создаёт MD5 контрольную сумму для текста с секретом."""
    combined = txt + secret
    return hashlib.md5(combined.encode('utf-8')).hexdigest()


def generate_qr_pdf(
    text: str,
    output_pdf: str,
    page_width: float = 595,
    page_height: float = 842,
    qr_width: float = 200,
    qr_height: float = 200,
    pos_x: float = 0,
    pos_y: float = 0
):
    """
    Генерирует PDF с QR-кодом текста.
    Можно указать размеры страницы, размеры QR и позицию QR.
    """
    # Генерация QR-кода
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Конвертируем в байтовый поток для PyMuPDF
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    # Создаём PDF
    pdf = fitz.open()
    page = pdf.new_page(width=page_width, height=page_height)

    # Вставка QR-кода
    rect = fitz.Rect(pos_x, pos_y, pos_x + qr_width, pos_y + qr_height)
    page.insert_image(rect, stream=img_bytes)

    pdf.save(output_pdf)
    pdf.close()
    print(f"PDF с QR-кодом сохранён: {output_pdf}")


# Пример использования
txt = "rpismo-answ-000000001"
secret = "secret"

checksum = generate_md5_checksum(txt, secret)
text_for_qr = f"{txt}-{checksum}"

# Генерация PDF с QR-кодом в правом верхнем углу
generate_qr_pdf(
    text=text_for_qr,
    output_pdf="_pymupdf.pdf",
    pos_x=0,  # левый верхний угол
    pos_y=0,
    qr_width=200,
    qr_height=200
)
