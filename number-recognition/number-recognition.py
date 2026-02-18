import fitz  # PyMuPDF
import cv2
import numpy as np
import easyocr
import re
import warnings

warnings.filterwarnings("ignore", category=UserWarning)


def preprocess_handwriting_with_lines(pix):
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if pix.n == 3 else cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    cnts = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    for c in cnts:
        cv2.drawContours(binary, [c], -1, (0, 0, 0), 2)
    processed = cv2.bitwise_not(binary)
    processed = cv2.GaussianBlur(processed, (3, 3), 0)
    return processed


def fix_ocr_errors(text):
    """Исправляет типичные ошибки EasyOCR в телефонных номерах."""
    # Кириллица/латиница которую путают с цифрами
    replacements = {
        'о': '0', 'О': '0', 'o': '0', 'O': '0',  # буква о -> ноль
        'l': '1', 'I': '1', 'i': '1',              # L/I -> единица
        'з': '3', 'З': '3',                          # з -> тройка
        'б': '6',                                    # б -> шестёрка
        'q': '9', 'g': '9',                          # q/g -> девятка
    }
    for wrong, right in replacements.items():
        text = text.replace(wrong, right)
    return text


def normalize(raw):
    """Приводит номер к формату +7XXXXXXXXXX."""
    raw = raw.replace(".", "-")
    raw = fix_ocr_errors(raw)
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 11:
        return None
    if digits.startswith("8"):
        digits = "7" + digits[1:]
    return f"+{digits}"


def run_ocr(pdf_path):
    reader = easyocr.Reader(['ru', 'en'], gpu=False)
    doc = fitz.open(pdf_path)
    found_phones = set()

    phone_regex = r'(?:\+7|8)[\s\.\-\(]*\d{3}[\s\.\-\)]*\d{3}[\s\.\-]*\d{2}[\s\.\-]*\d{2}'

    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
        clean_img = preprocess_handwriting_with_lines(pix)
        results = reader.readtext(clean_img, detail=0, paragraph=True, contrast_ths=0.1)
        text_block = " ".join(results)

        # Исправляем ошибки OCR ДО применения регулярки
        text_fixed = fix_ocr_errors(text_block)

        for raw in re.findall(phone_regex, text_fixed):
            phone = normalize(raw)
            if phone:
                found_phones.add(phone)

    return sorted(found_phones)


if __name__ == "__main__":
    path = "png2pdf.pdf"  # Твой файл
    print("Начинаю локальное распознавание...")
    results = run_ocr(path)
    print("\nНайденные номера:", results if results else "Ничего не найдено")