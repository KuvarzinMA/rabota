import hashlib
import qrcode
import io
import os
from fpdf import FPDF
from fpdf.enums import XPos, YPos


def generate_md5_checksum(txt: str, secret: str) -> str:
    return hashlib.md5((txt + secret).encode('utf-8')).hexdigest()


def create_blank(counter: int, secret: str, prison: str,
                               logo_1_path="logo_1.png",
                               logo_2_path="logo_2.png",
                               stencil_path="stencil.png",
                               obraz_path="obraz.png"):
    num = f"{counter:09d}"
    full_id = f"rpismo-answ-{num}"
    checksum = generate_md5_checksum(full_id, secret)
    qr_data = f"{full_id}-{checksum}"

    # --- QR ---
    qr = qrcode.QRCode(box_size=10, border=0)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")

    qr_rio = io.BytesIO()
    qr_img.save(qr_rio, format="PNG")
    qr_rio.seek(0)

    # --- PDF ---
    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # Шрифты
    pdf.add_font("ArialCustom", "", "C:/Windows/Fonts/arial.ttf")
    pdf.add_font("ArialCustom", "B", "C:/Windows/Fonts/arialbd.ttf")

    M = 9
    W = 210
    Y_start = 8

    # ================= ШАПКА =================
    if os.path.exists(logo_1_path):
        pdf.image(logo_1_path, x=M, y=Y_start, h=9)

    if os.path.exists(logo_2_path):
        pdf.image(logo_2_path, x=M + 40, y=Y_start + 1, h=7)

    pdf.set_font("ArialCustom", "B", 10)
    pdf.set_xy(110, Y_start)
    pdf.cell(W - M - 110, 5, f"Инициативное письмо № {num}",
             align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("ArialCustom", "", 8)
    pdf.set_x(110)
    pdf.cell(W - M - 110, 4, prison, align="R")

    Y_current = Y_start + 12
    pdf.set_line_width(0.3)
    pdf.line(M, Y_current, W - M, Y_current)

    # ================= QR + ФИО =================
    qr_size = 25
    pdf.image(qr_rio, x=M, y=Y_current + 4, w=qr_size, h=qr_size)

    pdf.set_font("ArialCustom", "", 6)
    pdf.text(M + 1, Y_current + 4 + qr_size + 3, "QR-код не портить")

    x_fields = M + 28

    # --- Отправитель ---
    y_sender_line = Y_current + 8
    pdf.set_line_width(0.2)
    pdf.line(x_fields, y_sender_line, W - 45, y_sender_line)  # Линия ФИО
    pdf.line(W - 40, y_sender_line, W - M, y_sender_line)  # Линия Даты

    pdf.set_font("ArialCustom", "B", 7)
    pdf.set_xy(x_fields, y_sender_line)
    pdf.cell(W - 45 - x_fields, 4, "Отправитель (ФИО)", align="C")
    pdf.set_xy(W - 40, y_sender_line)
    pdf.cell(30, 4, "Дата Рождения", align="C")

    # --- Получатель ---
    y_rec_line = y_sender_line + 10
    pdf.line(x_fields, y_rec_line, W - M, y_rec_line)

    pdf.set_xy(x_fields, y_rec_line)
    pdf.cell(W - 45 - x_fields, 4, "Получатель (ФИО)", align="C")

    # ================= ТЕЛЕФОН =================
    # Смещаем блок телефона ниже, чтобы не накладывался на подпись "Получатель"
    y_phone_block = y_rec_line + 10

    pdf.set_font("ArialCustom", "B", 5)
    pdf.set_xy(x_fields, y_phone_block)
    pdf.cell(80, -12, "МОБИЛЬНЫЙ НОМЕР ТЕЛЕФОНА ПОЛУЧАТЕЛЯ")

    # Трафарет
    if os.path.exists(stencil_path):
        pdf.image(stencil_path, x=x_fields, y=y_phone_block - 4, w=90, h=16)

    # Образец
    x_obr = W - M - 70
    pdf.set_xy(x_obr, y_phone_block)
    pdf.cell(40, -12, "ОБРАЗЕЦ НАПИСАНИЯ ЦИФР МОБИЛЬНОГО ТЕЛЕФОНА", align="L")

    if os.path.exists(obraz_path):
        pdf.image(obraz_path, x=x_obr, y=y_phone_block - 4, h=9)

    # Подпись под трафаретом
    pdf.set_font("ArialCustom", "", 6)
    pdf.set_xy(M + 121, y_phone_block + 7)
    pdf.cell(0, 4, "Мобильный номер заполняйте на каждом бланке. Пишите разборчиво.")

    # ================= РАЗДЕЛИТЕЛЬНАЯ ЛИНИЯ =================
    Y_WRITE_START = y_phone_block + 13
    pdf.set_line_width(0.3)
    pdf.line(M, Y_WRITE_START, W - M, Y_WRITE_START)

    # ================= ЛИНЕЙКА ДЛЯ ПИСЬМА =================
    pdf.set_draw_color(170, 170, 170)
    pdf.set_line_width(0.1)

    y_line = Y_WRITE_START + 7
    step = 6

    while y_line < 285:
        pdf.line(M, y_line, W - M, y_line)
        y_line += step

    # ================= ФУТЕР =================
    pdf.set_y(-12)
    pdf.set_font("ArialCustom", "B", 6)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(100, 5, "Не забудьте указать номер телефона", align="L")

    pdf.set_font("ArialCustom", "", 6)
    pdf.cell(0, 5, "Заполняя данный бланк пользователь подтверждает, что ознакомлен с офертой", align="R")

    output_path = f"init_{num}.pdf"
    pdf.output(output_path)
    print(f"Готово: {output_path}")


if __name__ == "__main__":
    create_blank(counter=1, secret="secret", prison="ФКУ СИЗО УФСИН")