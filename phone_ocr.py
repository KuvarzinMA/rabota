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
        """Определяет угол наклона листа"""
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

        # 2. Выравнивание горизонта
        angle = self._get_skew_angle(gray_full)
        (h_f, w_f) = gray_full.shape
        M = cv2.getRotationMatrix2D((w_f // 2, h_f // 2), angle, 1.0)
        gray_full = cv2.warpAffine(gray_full, M, (w_f, h_f), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # 3. Обрезка ROI (твои обновленные коэффициенты 0.05-0.35)
        y_start, y_end = int(h_f * 0.05), int(h_f * 0.35)
        x_start, x_end = 0, int(w_f * 0.55)
        roi_gray = gray_full[y_start:y_end, x_start:x_end].copy()
        roi_h, roi_w = roi_gray.shape

        # 4. Удаление QR-кода (белым цветом до бинаризации)
        qr_detector = cv2.QRCodeDetector()
        _, points, _ = qr_detector.detectAndDecode(roi_gray)
        if points is not None:
            cv2.fillPoly(roi_gray, points.astype(int), 255)
        else:
            # Резервный метод очистки области QR по градиенту
            grad = cv2.morphologyEx(roi_gray, cv2.MORPH_GRADIENT, np.ones((5, 5), np.uint8))
            _, qr_mask = cv2.threshold(grad, 60, 255, cv2.THRESH_BINARY)
            closed = cv2.morphologyEx(qr_mask, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
            cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                if cv2.contourArea(c) > 4000:
                    cv2.drawContours(roi_gray, [c], -1, 255, -1)

        # 5. Бинаризация и фильтрация "Анти-текст"
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(roi_gray)
        thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 21, 10)

        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # Удаляем линии, мелкий шум и слишком низкие объекты
            if w > 150 or cv2.contourArea(cnt) < 50 or h < 30:
                cv2.drawContours(thresh, [cnt], -1, 0, -1)

        # Создаем грубую маску для поиска координат и нарезки (чтобы цифры были целыми)
        process_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)

        # 6. Поиск контуров цифр
        final_contours, _ = cv2.findContours(process_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rects = []
        for c in final_contours:
            x, y, w, h = cv2.boundingRect(c)
            # Фильтр "коридора" индекса
            if 40 < h < 180 and (roi_h * 0.2 < y < roi_h * 0.95):
                rects.append((x, y, w, h))

        # Сортируем слева направо
        rects = sorted(rects, key=lambda r: r[0])

        full_index = ""
        # 7. Обработка каждой цифры для нейросети
        for (x, y, w, h) in rects:
            p = 8  # Отступ
            y1, y2 = max(0, y - p), min(roi_h, y + h + p)
            x1, x2 = max(0, x - p), min(roi_w, x + w + p)

            # Вырезаем из ЖИРНОЙ маски (process_img)
            digit_roi = process_img[y1:y2, x1:x2]
            if digit_roi.size == 0:
                continue

            # Подготовка квадрата 32x32
            final_roi = np.zeros((32, 32), dtype="uint8")

            # Увеличиваем масштаб до 28 пикселей для лучшей детализации
            target_side = 28.0
            scale = target_side / max(digit_roi.shape)
            nw, nh = int(digit_roi.shape[1] * scale), int(digit_roi.shape[0] * scale)

            # Используем INTER_CUBIC для плавных линий при ресайзе
            roi_res = cv2.resize(digit_roi, (nw, nh), interpolation=cv2.INTER_CUBIC)

            # Убираем серые пиксели и делаем локальное жирнение внутри 32x32
            _, roi_res = cv2.threshold(roi_res, 100, 255, cv2.THRESH_BINARY)
            roi_res = cv2.dilate(roi_res, np.ones((2, 2), np.uint8), iterations=1)

            # Центрируем в 32x32
            dy, dx = (32 - nh) // 2, (32 - nw) // 2
            final_roi[dy:dy + nh, dx:dx + nw] = roi_res

            # Predict
            roi_input = (final_roi.astype("float32") / 255.0).reshape(1, 32, 32, 1)
            prediction = self.model.predict(roi_input, verbose=0)
            full_index += str(np.argmax(prediction))

        return full_index if full_index else None