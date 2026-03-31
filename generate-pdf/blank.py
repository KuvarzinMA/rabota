import fitz
import qrcode
import io
import hashlib
import os
from fitz import Point, Rect


def generate_md5_checksum(txt: str, secret: str) -> str:
    return hashlib.md5((txt + secret).encode('utf-8')).hexdigest()


def create_perfect_blank(counter: int, secret: str,
                         logo_path="logo.png",
                         stencil_path="stencil.png",
                         obraz_path="obraz.png",
                         w=595, h=842):
    num = f"{counter:09d}"
    full_id = f"rpismo-answ-{num}"
    checksum = generate_md5_checksum(full_id, secret)
    qr_data = f"{full_id}-{checksum}"

    # QR-код
    qr = qrcode.QRCode(box_size=4, border=0)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    bio = io.BytesIO()
    img.save(bio, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=w, height=h)

    # Шрифты
    font_regular = "C:/Windows/Fonts/arial.ttf"
    font_bold = "C:/Windows/Fonts/arialbd.ttf"
    page.insert_font(fontname="f_reg", fontfile=font_regular)
    page.insert_font(fontname="f_bold", fontfile=font_bold)
    fr = "f_reg"
    fb = "f_bold"

    M = 25
    y_qr = 22

    # ====================== ШАПКА ======================

    # 1. QR-код
    qr_size = 70
    page.insert_image(Rect(M, y_qr, M + qr_size, y_qr + qr_size), stream=bio.getvalue())
    page.insert_text((M + 2, y_qr + qr_size + 8), "QR-код не портить", fontsize=6, fontname=fr)

    # 2. Логотип
    logo_w, logo_h = 160, 100
    logo_left = w - M - logo_w
    if os.path.exists(logo_path):
        page.insert_image(
            Rect(logo_left, y_qr - 18, logo_left + logo_w, y_qr - 18 + logo_h),
            filename=logo_path
        )

    # 3. Текст по центру
    header_center_x = (M + qr_size + logo_left) / 2
    y_text = y_qr + 14
    page.insert_text((header_center_x - 90, y_text), f"Бланк письма № {num}", fontsize=9, fontname=fb)
    page.insert_text((header_center_x - 65, y_text + 12), "Оплата получателем", fontsize=8.5, fontname=fb)
    page.insert_text((header_center_x - 100, y_text + 25), "ФКУ СИЗО-{НОМЕР} УФСИН России по {...}", fontsize=7.2,
                     fontname=fr)

    # Линия под шапкой
    y_main = y_qr + 85
    page.draw_line(Point(M, y_main), Point(w - M, y_main), width=1.0)

    # ====================== ОСНОВНОЙ БЛОК ======================
    y_content = y_main + 15

    # --- ЛЕВАЯ ЧАСТЬ: Телефон и Образец ---
    x_phone_block = M

    page.insert_text((x_phone_block, y_content), "МОБИЛЬНЫЙ НОМЕР ПОЛУЧАТЕЛЯ", fontsize=7.6, fontname=fb)
    if os.path.exists(stencil_path):
        # Трафарет
        page.insert_image(Rect(x_phone_block, y_content + 6, x_phone_block + 185, y_content + 42),
                          filename=stencil_path)

    y_obraz = y_content + 50
    page.insert_text((x_phone_block, y_obraz), "ОБРАЗЕЦ ЗАПОЛНЕНИЯ", fontsize=7.6, fontname=fb)
    if os.path.exists(obraz_path):
        # Образец: ширина 110, высота 32
        page.insert_image(Rect(x_phone_block, y_obraz + 4, x_phone_block + 110, y_obraz + 36), filename=obraz_path)

    # --- ПРАВАЯ ЧАСТЬ: ФИО ---
    x_fio_start = M + 205
    fio_line_end = w - M

    # ФИО Отправителя
    page.insert_text((x_fio_start, y_content), "ФИО ОТПРАВИТЕЛЯ", fontsize=7.8, fontname=fb)
    page.insert_text((fio_line_end - 75, y_content), "ГОД РОЖДЕНИЯ", fontsize=7.8, fontname=fb)

    page.draw_line(Point(x_fio_start, y_content + 25), Point(fio_line_end - 85, y_content + 25), width=0.85)
    page.draw_line(Point(fio_line_end - 75, y_content + 25), Point(fio_line_end, y_content + 25), width=0.85)

    # ФИО Получателя
    y_fio_rec = y_content + 40
    page.insert_text((x_fio_start, y_fio_rec), "ФИО ПОЛУЧАТЕЛЯ", fontsize=7.8, fontname=fb)
    page.draw_line(Point(x_fio_start, y_fio_rec + 25), Point(fio_line_end, y_fio_rec + 25), width=0.85)

    # Инструкция
    page.insert_text((M, y_fio_rec + 48),
                     "Мобильный номер телефона заполняйте на каждом бланке. Пишите разборчиво печатными буквами.",
                     fontsize=6, fontname=fr)

    # ====================== ФУТЕР ======================
    fy = h - 25
    page.insert_text((M, fy), "Не забудьте указать номер телефона", fontsize=6.2, fontname=fb)
    page.insert_text((w - M - 245, fy),
                     "Заполняя бланк, пользователь подтверждает согласие с условиями оферты",
                     fontsize=5.4, fontname=fr)

    doc.save(f"blank_{num}.pdf")
    doc.close()
    print(f"Файл blank_{num}.pdf готов.")


create_perfect_blank(counter=1, secret="secret")