import fitz  # PyMuPDF
import qrcode
import io
import hashlib
import os
from fitz import Point


def generate_md5_checksum(txt: str, secret: str) -> str:
    combined = txt + secret
    return hashlib.md5(combined.encode('utf-8')).hexdigest()


def create_final_header(
        counter: int,
        secret: str,
        logo_path: str = "logo.png",
        phone_stencil_path: str = "stencil.png",
        obraz_path: str = "obraz.png",
        page_width: float = 595,
        page_height: float = 842
):
    full_id = f"rpismo-wsna-{counter:09d}"
    display_number = f"{counter:09d}"
    checksum = generate_md5_checksum(full_id, secret)
    text_for_qr = f"{full_id}-{checksum}"
    output_pdf = f"init_{display_number}.pdf"

    # 1. QR-код
    qr = qrcode.QRCode(version=1, box_size=10, border=0)
    qr.add_data(text_for_qr)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=page_width, height=page_height)

    # --- ГЕОМЕТРИЯ ---
    margin = 25
    top_y = 25
    qr_size = 75
    col_right_w = 140
    logo_h = 40
    stencil_h = 35
    obraz_h = 22

    # QR-код слева
    qr_rect = fitz.Rect(margin, top_y, margin + qr_size, top_y + qr_size)
    page.insert_image(qr_rect, stream=img_bytes.getvalue())

    # --- ПРАВАЯ КОЛОНКА (Лого -> Трафарет -> Образец) ---
    curr_y = top_y
    right_x_start = page_width - margin - col_right_w
    right_x_end = page_width - margin

    # Лого
    if os.path.exists(logo_path):
        page.insert_image(fitz.Rect(right_x_start, curr_y, right_x_end, curr_y + logo_h),
                          filename=logo_path, keep_proportion=True)
        curr_y += logo_h + 3  # Зазор под лого

    # Трафарет
    if os.path.exists(phone_stencil_path):
        page.insert_image(fitz.Rect(right_x_start, curr_y, right_x_end, curr_y + stencil_h),
                          filename=phone_stencil_path, keep_proportion=True)
        curr_y += stencil_h + 1  # МИНИМАЛЬНЫЙ зазор до образца

    # Образец (почти вплотную к трафарету)
    if os.path.exists(obraz_path):
        page.insert_image(fitz.Rect(right_x_start, curr_y, right_x_end, curr_y + obraz_h),
                          filename=obraz_path, keep_proportion=True)
        curr_y += obraz_h

    # --- ШРИФТЫ ---
    f_b_path = "C:/Windows/Fonts/arialbd.ttf"
    f_reg_path = "C:/Windows/Fonts/arial.ttf"
    f_bold = "f_bold" if os.path.exists(f_b_path) else "helv-bold"
    f_reg = "f_reg" if os.path.exists(f_reg_path) else "helv"
    if "f_bold" in f_bold: page.insert_font(fontname=f_bold, fontfile=f_b_path)
    if "f_reg" in f_reg: page.insert_font(fontname=f_reg, fontfile=f_reg_path)

    bold_font_obj = fitz.Font(fontfile=f_b_path) if "f_bold" in f_bold else None

    # --- ЗАГОЛОВОК (ПО ЦЕНТРУ СТРАНИЦЫ) ---
    center_x = page_width / 2
    title = f"Инициативное письмо № {display_number}"
    t_size = 13
    t_len = bold_font_obj.text_length(title, fontsize=t_size) if bold_font_obj else 200
    page.insert_text((center_x - t_len / 2, top_y + 15), title, fontsize=t_size, fontname=f_bold)

    # --- ПОЛЯ ВВОДА ---
    avail_start_x = margin + qr_size + 15
    avail_end_x = right_x_start - 15

    line_y1 = top_y + 45
    line_y2 = top_y + 70

    # От кого
    page.insert_text((avail_start_x, line_y1 - 3), "От кого:", fontsize=9, fontname=f_reg)
    page.draw_line(Point(avail_start_x + 40, line_y1), Point(avail_end_x, line_y1), color=(0, 0, 0), width=0.7)

    # Кому
    page.insert_text((avail_start_x, line_y2 - 3), "Кому:", fontsize=9, fontname=f_reg)
    page.draw_line(Point(avail_start_x + 40, line_y2), Point(avail_end_x, line_y2), color=(0, 0, 0), width=0.7)

    # --- ФИНАЛЬНАЯ ЧЕРТА ---
    final_y = max(top_y + qr_size, curr_y) + 10
    page.draw_line(Point(margin, final_y), Point(page_width - margin, final_y), color=(0, 0, 0), width=1.5)

    doc.save(output_pdf)
    doc.close()
    print(f"Готово: {output_pdf}")


# --- ЗАПУСК ---
create_final_header(counter=1, secret="secret")