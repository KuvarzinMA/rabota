import cv2
import numpy as np
import tensorflow as tf
import fitz
import os
from config import MODEL_PATH


class PhoneOCR:
    def __init__(self):
        # Загружаем модель один раз при инициализации класса
        if os.path.exists(MODEL_PATH):
            self.model = tf.keras.models.load_model(MODEL_PATH)
            print(f"Модель {MODEL_PATH} успешно загружена.")
        else:
            self.model = None
            print(f"ВНИМАНИЕ: Файл модели {MODEL_PATH} не найден!")

    def _get_skew_angle(self, gray_img):
        """Определяет угол наклона"""
        edges = cv2.Canny(gray_img, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 200, minLineLength=150, maxLineGap=20)
        angles = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                if -15 < angle < 15:
                    angles.append(angle)
        return np.median(angles) if angles else 0

    def extract_phone(self, pdf_bytes):
        """Основной метод распознавания номера из байтов PDF"""
        if self.model is None:
            return None

        # 1. Загрузка страницы из памяти
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 2. Выравнивание
        angle = self._get_skew_angle(gray_full)
        (h_f, w_f) = gray_full.shape
        M = cv2.getRotationMatrix2D((w_f // 2, h_f // 2), angle, 1.0)
        gray_full = cv2.warpAffine(gray_full, M, (w_f, h_f), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # 3. Обрезка ROI (твои коэффициенты)
        roi_h_limit = int(h_f * 0.25)
        roi_w_limit = int(w_f * 0.55)
        roi_gray = gray_full[0:roi_h_limit, 0:roi_w_limit]

        # 4. Бинаризация
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(roi_gray)
        thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 21, 10)

        # 5. ТВОЯ ФИЛЬТРАЦИЯ "АНТИ-ТЕКСТ"
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = w / float(h)
            area = cv2.contourArea(cnt)

            # Удаляем маркеры
            if w > 150 and y < (roi_h_limit * 0.3):
                cv2.drawContours(thresh, [cnt], -1, 0, -1)
            # Удаляем сетку и мелкий текст
            if area < 50 or h < 30:
                cv2.drawContours(thresh, [cnt], -1, 0, -1)
            # Удаляем широкие буквы
            if aspect_ratio > 1.2 and y > (roi_h_limit * 0.5):
                cv2.drawContours(thresh, [cnt], -1, 0, -1)

        process_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)

        # 6. Нарезка на цифры
        final_contours, _ = cv2.findContours(process_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rects = []
        for c in final_contours:
            x, y, w, h = cv2.boundingRect(c)
            # Попадание в "коридор" индекса
            if 40 < h < 180 and (roi_h_limit * 0.25 < y < roi_h_limit * 0.95):
                rects.append((x, y, w, h))

        # Сортируем слева направо
        rects = sorted(rects, key=lambda r: r[0])

        full_index = ""
        for (x, y, w, h) in rects[:11]:
            p = 10  # padding
            digit_roi = process_img[max(0, y - p):min(roi_gray.shape[0], y + h + p),
                        max(0, x - p):min(roi_gray.shape[1], x + w + p)]
            if digit_roi.size == 0:
                continue

            # Подготовка картинки 32x32 для CNN
            final_roi = np.zeros((32, 32), dtype="uint8")
            scale = 22.0 / max(digit_roi.shape)
            nw, nh = int(digit_roi.shape[1] * scale), int(digit_roi.shape[0] * scale)
            roi_res = cv2.resize(digit_roi, (nw, nh))

            # Центрируем
            start_y = (32 - nh) // 2
            start_x = (32 - nw) // 2
            final_roi[start_y:start_y + nh, start_x:start_x + nw] = roi_res

            # Predict
            roi_input = final_roi.astype("float32") / 255.0
            roi_input = np.expand_dims(np.expand_dims(roi_input, axis=-1), axis=0)

            prediction = self.model.predict(roi_input, verbose=0)
            full_index += str(np.argmax(prediction))

        return full_index if full_index else None