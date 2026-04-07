import os
from fpdf import FPDF
from fpdf.enums import XPos, YPos


def validate_fio(name: str):
    if any(char.isdigit() for char in name):
        raise ValueError(f"Ошибка: ФИО '{name}' содержит цифры!")
    return name.strip()


def draw_text_fit(pdf, text, x, y, max_w, default_size=11):
    """Печать текста с автоматическим уменьшением шрифта, если не влезает."""
    current_size = default_size
    pdf.set_font("ArialCustom", "", current_size)
    while pdf.get_string_width(text) > max_w and current_size > 6:
        current_size -= 0.5
        pdf.set_font("ArialCustom", "", current_size)

    pdf.text(x, y - 1.5, text)  # Печатаем чуть выше линии


def draw_message_text(pdf, text, x, start_y, max_w, step, max_y):
    if len(text) > 2000:
        text = text[:2000]

    pdf.set_font("ArialCustom", "", 11)
    lines = pdf.multi_cell(w=max_w, h=step, text=text, dry_run=True, output="LINES")

    current_y = start_y
    for line in lines:
        if current_y > max_y:
            break
        # Печатаем текст, чуть приподняв над линией (на 1.5 мм)
        pdf.text(x, current_y - 1.5, line)
        current_y += step


def create_blank(counter: int, prison: str,
                 sender_fio="", sender_bday="", recipient_fio="",
                 message_text="",
                 logo_1_path="logo_1.png",
                 logo_2_path="logo_2.png"):
    sender_fio = validate_fio(sender_fio)
    recipient_fio = validate_fio(recipient_fio)

    num = f"{counter:09d}"
    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    pdf.add_font("ArialCustom", "", "C:/Windows/Fonts/arial.ttf")
    pdf.add_font("ArialCustom", "B", "C:/Windows/Fonts/arialbd.ttf")

    M = 9
    W = 210
    Y_start = 8
    CONTENT_FONT_SIZE = 11  # Единый размер для заполняемых данных

    # ================= ШАПКА =================
    if os.path.exists(logo_1_path):
        pdf.image(logo_1_path, x=M, y=Y_start, h=9)
    if os.path.exists(logo_2_path):
        pdf.image(logo_2_path, x=M + 40, y=Y_start + 1, h=7)

    pdf.set_font("ArialCustom", "B", 10)
    pdf.set_xy(110, Y_start)
    pdf.cell(W - M - 110, 5, f"Бланк письма № {num}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("ArialCustom", "", 8)
    pdf.set_x(110)
    pdf.cell(W - M - 110, 4, prison, align="R")

    Y_current = Y_start + 12
    pdf.set_line_width(0.3)
    pdf.line(M, Y_current, W - M, Y_current)

    # ================= БЛОК ОТПРАВИТЕЛЯ =================
    y_line_1 = Y_current + 12

    # ФИО Отправителя
    draw_text_fit(pdf, sender_fio, M, y_line_1, max_w=(W - 45 - M), default_size=CONTENT_FONT_SIZE)
    # Дата рождения
    draw_text_fit(pdf, sender_bday, W - 40, y_line_1, max_w=31, default_size=CONTENT_FONT_SIZE)

    pdf.set_line_width(0.2)
    pdf.line(M, y_line_1, W - 45, y_line_1)
    pdf.line(W - 40, y_line_1, W - M, y_line_1)

    pdf.set_font("ArialCustom", "B", 7)
    pdf.set_xy(M, y_line_1)
    pdf.cell(W - 45 - M, 4, "Отправитель (ФИО)", align="C")
    pdf.set_xy(W - 40, y_line_1)
    pdf.cell(31, 4, "Дата Рождения", align="C")

    # ================= БЛОК ПОЛУЧАТЕЛЯ =================
    y_line_2 = y_line_1 + 12  # Одинаковый шаг со вторым блоком

    # ФИО Получателя (используем ту же функцию и тот же размер шрифта)
    draw_text_fit(pdf, recipient_fio, M, y_line_2, max_w=(W - M - M), default_size=CONTENT_FONT_SIZE)

    pdf.line(M, y_line_2, W - M, y_line_2)
    pdf.set_font("ArialCustom", "B", 7)
    pdf.set_xy(M, y_line_2)
    pdf.cell(W - 45 - M, 4, "Получатель (ФИО)", align="C")

    # ================= ТЕКСТ ПИСЬМА =================
    Y_WRITE_START = y_line_2 + 8
    pdf.set_line_width(0.3)
    pdf.set_draw_color(0, 0, 0)
    pdf.line(M, Y_WRITE_START, W - M, Y_WRITE_START)

    pdf.set_draw_color(170, 170, 170)
    pdf.set_line_width(0.1)

    y_line = Y_WRITE_START + 7
    step = 6
    max_page_y = 285

    while y_line < max_page_y:
        pdf.line(M, y_line, W - M, y_line)
        y_line += step

    if message_text:
        draw_message_text(pdf, message_text, M + 1, Y_WRITE_START + 7, W - 2 * M - 2, step, max_page_y)

    output_path = f"rodstv_{num}.pdf"
    pdf.output(output_path)
    print(f"Готово: {output_path}")


if __name__ == "__main__":
    create_blank(
        counter=1,
        prison="СИЗО-100 УФСИН РОССИИ",
        sender_fio="Иванов Иван Иванович",
        sender_bday="15.05.1985",
        recipient_fio="Петров Петр Петрович",
        message_text="Привет! Это тестовое письмо."
    )