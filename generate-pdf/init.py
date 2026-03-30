import fitz  # PyMuPDF
from fitz import Point
import qrcode
import io
import hashlib
import os


def generate_md5_checksum(txt: str, secret: str) -> str:
    combined = txt + secret
    return hashlib.md5(combined.encode('utf-8')).hexdigest()


def create_clean_blank(
        counter: int,
        secret: str,
        logo_path: str = None,
        phone_stencil_path: str = None,
        page_width: float = 595,
        page_height: float = 842
):
    full_id = f"rpismo-wsna-{counter:09d}"
    display_number = f"{counter:09d}"
    checksum = generate_md5_checksum(full_id, secret)
    text_for_qr = f"{full_id}-{checksum}"
    output_pdf = f"init_{counter:09d}.pdf"

    # 1. QR-код (Черный, классический)
    qr = qrcode.QRCode(version=1, box_size=10, border=0)
    qr.add_data(text_for_qr)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=page_width, height=page_height)

    # --- ГЕОМЕТРИЯ (Смещаем к краям) ---
    margin = 25  # Уменьшили отступ от края (было 40)
    top_y = 25  # Выше к верхнему краю
    qr_size = 75  # Оптимальный размер QR
    logo_w = 110  # Логотип больше
    logo_h = 45
    stencil_w = 140  # Трафарет больше
    stencil_h = 40

    # QR-код (К самому левому краю)
    qr_rect = fitz.Rect(margin, top_y, margin + qr_size, top_y + qr_size)
    page.insert_image(qr_rect, stream=img_bytes.getvalue())

    # Логотип (К самому правому краю)
    if logo_path and os.path.exists(logo_path):
        logo_rect = fitz.Rect(page_width - margin - logo_w, top_y, page_width - margin, top_y + logo_h)
        page.insert_image(logo_rect, filename=logo_path, keep_proportion=True)

    # Трафарет (Под логотипом, тоже крупно)
    if phone_stencil_path and os.path.exists(phone_stencil_path):
        # Зазор между лого и трафаретом всего 5 пикселей для плотности
        stencil_y = top_y + logo_h + 5
        stencil_rect = fitz.Rect(page_width - margin - stencil_w, stencil_y, page_width - margin, stencil_y + stencil_h)
        page.insert_image(stencil_rect, filename=phone_stencil_path, keep_proportion=True)

    # --- ШРИФТЫ ---
    f_path = "C:/Windows/Fonts/arial.ttf"
    f_b_path = "C:/Windows/Fonts/arialbd.ttf"
    f_reg = "f_reg";
    f_bold = "f_bold"
    if os.path.exists(f_path): page.insert_font(fontname=f_reg, fontfile=f_path)
    if os.path.exists(f_b_path): page.insert_font(fontname=f_bold, fontfile=f_b_path)
    b_font = fitz.Font(fontfile=f_b_path) if os.path.exists(f_b_path) else None

    # --- ТЕКСТ ПО ЦЕНТРУ ---
    center_x = page_width / 2

    # Заголовок (Жирный, крупный)
    header_text = f"Инициативное письмо № {display_number}"
    h_size = 15
    h_len = b_font.text_length(header_text, fontsize=h_size) if b_font else 200
    page.insert_text((center_x - h_len / 2, top_y + 15), header_text, fontsize=h_size, fontname=f_bold)

    # Поля ввода (Длинные линии в центре)
    field_size = 10
    # Линии начинаются сразу после QR и заканчиваются перед трафаретом
    text_x = margin + qr_size + 15
    line_end_x = page_width - margin - stencil_w - 15

    # От кого
    page.insert_text((text_x, top_y + 45), "От кого:", fontsize=field_size, fontname=f_reg)
    page.draw_line(fitz.Point(text_x + 45, top_y + 47), fitz.Point(line_end_x, top_y + 47), color=(0, 0, 0), width=0.8)

    # Кому
    page.insert_text((text_x, top_y + 70), "Кому:", fontsize=field_size, fontname=f_reg)
    page.draw_line(fitz.Point(text_x + 45, top_y + 72), Point(line_end_x, top_y + 72), color=(0, 0, 0), width=0.8)

    # --- РАЗДЕЛИТЕЛЬНАЯ ЛИНИЯ ---
    # Линия под всей "шапкой"
    line_y = top_y + logo_h + stencil_h + 5
    page.draw_line(fitz.Point(margin, line_y), fitz.Point(page_width - margin, line_y), color=(0, 0, 0), width=1.5)

    doc.save(output_pdf)
    doc.close()
    print(f"Файл {output_pdf} создан.")


# --- ЗАПУСК ---
for i in range(1, 2):
    create_clean_blank(
        counter=i,
        secret="secret",
        logo_path="logo.png",
        phone_stencil_path="stencil.png"
    )