import qrcode
import hashlib


def generate_md5_checksum(txt: str, secret: str) -> str:
    """Создаёт MD5 контрольную сумму для текста с секретом."""
    combined = txt + secret
    return hashlib.md5(combined.encode('utf-8')).hexdigest()


def generate_qr_image(text: str, output_image: str, size: int = 400):
    """
    Генерирует QR-код с текстом и сохраняет как картинку.
    size: размер QR-кода в пикселях
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # масштабируем изображение до нужного размера
    img = img.resize((size, size))

    img.save(output_image)
    print(f"QR-код сохранён в {output_image}")


# Пример использования
txt = "rpismo-answ-000000001"
secret = "secret"
checksum = generate_md5_checksum(txt, secret)
text_for_qr = f"{txt}-{checksum}"

generate_qr_image(text_for_qr, "qr_image.png", size=400)
