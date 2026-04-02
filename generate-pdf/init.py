import hashlib
import qrcode
import io
import os
from fpdf import FPDF
from fpdf.enums import XPos, YPos


def generate_md5_checksum(txt: str, secret: str) -> str:
    return hashlib.md5((txt + secret).encode('utf-8')).hexdigest()


def create_blank_fpdf(counter: int, secret: str,
                              logo_path="logo.png"):
    num = f"{counter:09d}"
    full_id = f"rpismo-wsna-{num}"
    checksum = generate_md5_checksum(full_id, secret)
    qr_data = f"{full_id}-{checksum}"

    # --- Генерация QR-кода ---
    qr = qrcode.QRCode(box_size=10, border=0)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")

    qr_rio = io.BytesIO()
    qr_img.save(qr_rio, format="PNG")
    qr_rio.seek(0)

    # --- Инициализация PDF ---
    pdf = FPDF(orientation="P", unit="mm", format="A4")

    # 1. ЗАПРЕТ ПЕРЕНОСА СТРАНИЦЫ (чтобы всегда был 1 лист)
    pdf.set_auto_page_break(auto=False)

    pdf.add_page()

    # Шрифты
    font_reg = "C:/Windows/Fonts/arial.ttf"
    font_bold = "C:/Windows/Fonts/arialbd.ttf"
    pdf.add_font("Arial", "", font_reg)
    pdf.add_font("Arial", "B", font_bold)

    M = 10  # Поля
    y_qr = 8  # Начальная точка
    W_PAGE = 210

    # ====================== ШАПКА ======================

    # 1. QR-код
    qr_size = 25
    pdf.image(qr_rio, x=M, y=y_qr, w=qr_size, h=qr_size)
    pdf.set_font("Arial", "", 6)
    pdf.text(M + 1, y_qr + qr_size + 3, "QR-код не портить")

    # 2. Логотип
    logo_w = 56
    logo_x = W_PAGE - M - logo_w
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=logo_x, y=y_qr, w=logo_w)

    # 3. Текст по центру
    pdf.set_font("Arial", "B", 9)
    pdf.set_y(y_qr + 5)
    pdf.set_x(M + qr_size)

    content_w = logo_x - (M + qr_size)
    pdf.cell(content_w, 5, f"Инициативное письмо № {num}", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Arial", "B", 8.5)
    pdf.set_x(M + qr_size)
    pdf.cell(content_w, 5, "Оплата получателем", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Arial", "", 7.2)
    pdf.set_x(M + qr_size)
    pdf.cell(content_w, 4, "ФКУ СИЗО-{НОМЕР} УФСИН России по {...}", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Линия под шапкой
    y_line = y_qr + 30
    pdf.set_line_width(0.3)
    pdf.line(M, y_line, W_PAGE - M, y_line)

    # ====================== ОСНОВНОЙ БЛОК ======================
    y_content = y_line + 6

    pdf.set_font("Arial", "B", 7.6)
    pdf.set_xy(M, y_content)


    y_obraz = y_content + 18
    pdf.set_xy(M, y_obraz)


    x_fio = M
    pdf.set_font("Arial", "B", 7.8)
    pdf.set_xy(x_fio, y_content - 2)
    pdf.cell(0, 0, "ОТПРАВИТЕЛЬ (ФИО)")

    pdf.set_xy(W_PAGE - M - 25, y_content - 2)
    pdf.cell(25, 0, "ГОД РОЖДЕНИЯ", align="R")

    pdf.line(x_fio, y_content + 8, W_PAGE - M - 30, y_content + 8)
    pdf.line(W_PAGE - M - 25, y_content + 8, W_PAGE - M, y_content + 8)

    y_fio_rec = y_content + 14
    pdf.set_xy(x_fio, y_fio_rec - 2)
    pdf.cell(0, 0, "ПОЛУЧАТЕЛЬ (ФИО)")
    pdf.line(x_fio, y_fio_rec + 8, W_PAGE - M, y_fio_rec + 8)

    pdf.set_font("Arial", "", 6)
    pdf.set_xy(M, y_fio_rec + 13)
    pdf.cell(0, 0, "Информация . . . . . . Пишите разборчиво печатными буквами.")

    # Финальная черта, после которой начинается пустое место для письма
    y_content_start = pdf.get_y() + 4
    pdf.set_draw_color(200, 200, 200)  # Светло-серая линия
    pdf.line(M, y_content_start, W_PAGE - M, y_content_start)

    # ====================== ФУТЕР ======================
    pdf.set_y(-12)
    pdf.set_font("Arial", "B", 6.2)
    pdf.cell(100, 0, "Информация . . .")

    pdf.set_font("Arial", "", 5.4)
    pdf.cell(0, 0, "Заполняя бланк, пользователь подтверждает согласие с условиями оферты", align="R")

    # --- Сохранение ---
    output_path = f"init_{num}.pdf"
    pdf.output(output_path)
    print(f"Готово! Файл {output_path} создан.")


if __name__ == "__main__":
    create_blank_fpdf(counter=1, secret="secret")