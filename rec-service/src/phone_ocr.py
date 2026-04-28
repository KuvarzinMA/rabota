import cv2
import numpy as np
import tensorflow as tf
import fitz
import os
from src.config import MODEL_PATH


class PhoneOCR:
    def __init__(self):
        self.model = None

        if os.path.exists(MODEL_PATH):
            try:
                self.model = tf.keras.models.load_model(MODEL_PATH)
                print(f"[OK] Модель загружена: {MODEL_PATH}")
                print(f"[INFO] Input shape: {self.model.input_shape}")
            except Exception as e:
                print(f"[ERROR] Ошибка загрузки модели: {e}")
        else:
            print(f"[ERROR] Модель не найдена: {MODEL_PATH}")

    # -------------------------
    # Угол наклона
    # -------------------------
    def _get_skew_angle(self, gray):
        edges = cv2.Canny(gray, 50, 150)

        lines = cv2.HoughLinesP(
            edges,
            1,
            np.pi / 180,
            threshold=150,
            minLineLength=100,
            maxLineGap=20
        )

        if lines is None:
            return 0

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))

            if -15 < angle < 15:
                angles.append(angle)

        return np.median(angles) if angles else 0

    # -------------------------
    # Pixmap → OpenCV
    # -------------------------
    def _pix_to_cv(self, pix):
        n_channels = pix.n
        img = np.frombuffer(pix.samples, dtype=np.uint8)
        img = img.reshape(pix.h, pix.w, n_channels)

        if n_channels == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif n_channels == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif n_channels == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

        return img

    # -------------------------
    # Удаление QR
    # -------------------------
    def _remove_qr(self, roi_gray):
        qr_detector = cv2.QRCodeDetector()

        roi_color = cv2.cvtColor(roi_gray, cv2.COLOR_GRAY2BGR)
        _, points, _ = qr_detector.detectAndDecode(roi_color)

        if points is not None:
            cv2.fillPoly(roi_gray, points.astype(int), 255)
            return roi_gray

        # fallback
        grad = cv2.morphologyEx(
            roi_gray,
            cv2.MORPH_GRADIENT,
            np.ones((5, 5), np.uint8)
        )

        _, mask = cv2.threshold(grad, 60, 255, cv2.THRESH_BINARY)

        closed = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            np.ones((25, 25), np.uint8)
        )

        contours, _ = cv2.findContours(
            closed,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for c in contours:
            if cv2.contourArea(c) > 3000:
                cv2.drawContours(roi_gray, [c], -1, 255, -1)

        return roi_gray

    # -------------------------
    # Подготовка цифры
    # -------------------------
    def _prepare_digit(self, digit_roi):
        if digit_roi.size == 0:
            return None

        target_size = 32
        final = np.zeros((target_size, target_size), dtype="uint8")

        scale = 28.0 / max(digit_roi.shape)
        nw = max(1, int(digit_roi.shape[1] * scale))
        nh = max(1, int(digit_roi.shape[0] * scale))

        resized = cv2.resize(
            digit_roi,
            (nw, nh),
            interpolation=cv2.INTER_CUBIC
        )

        _, resized = cv2.threshold(resized, 100, 255, cv2.THRESH_BINARY)
        resized = cv2.dilate(resized, np.ones((2, 2), np.uint8), 1)

        dy = (target_size - nh) // 2
        dx = (target_size - nw) // 2

        final[dy:dy + nh, dx:dx + nw] = resized

        final = final.astype("float32") / 255.0
        final = final.reshape(1, 32, 32, 1)

        return final

    # -------------------------
    # Основной метод
    # -------------------------
    def extract_phone(self, pdf_bytes):
        if self.model is None:
            print("[ERROR] Модель не загружена")
            return None

        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                page = doc[0]

                pix = page.get_pixmap(matrix=fitz.Matrix(4, 4))
                img = self._pix_to_cv(pix)

        except Exception as e:
            print(f"[ERROR] PDF обработка: {e}")
            return None

        # grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # deskew
        angle = self._get_skew_angle(gray)
        h, w = gray.shape

        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        gray = cv2.warpAffine(
            gray,
            M,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

        # ROI
        y1, y2 = int(h * 0.05), int(h * 0.35)
        x1, x2 = 0, int(w * 0.55)

        roi = gray[y1:y2, x1:x2].copy()
        roi_h, roi_w = roi.shape

        # remove QR
        roi = self._remove_qr(roi)

        # enhance
        clahe = cv2.createCLAHE(clipLimit=3.0)
        enhanced = clahe.apply(roi)

        thresh = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            21,
            10
        )

        # очистка мусора
        contours, _ = cv2.findContours(
            thresh,
            cv2.RETR_TREE,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)

            if w > 150 or cv2.contourArea(cnt) < 30 or h < 20:
                cv2.drawContours(thresh, [cnt], -1, 0, -1)

        # утолщение
        proc = cv2.dilate(thresh, np.ones((2, 2), np.uint8), 1)

        # поиск цифр
        contours, _ = cv2.findContours(
            proc,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        rects = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)

            if 40 < h < 180 and (roi_h * 0.2 < y < roi_h * 0.95):
                rects.append((x, y, w, h))

        rects = sorted(rects, key=lambda r: r[0])

        result = ""

        for (x, y, w, h) in rects:
            pad = 8

            yy1 = max(0, y - pad)
            yy2 = min(roi_h, y + h + pad)
            xx1 = max(0, x - pad)
            xx2 = min(roi_w, x + w + pad)

            digit = proc[yy1:yy2, xx1:xx2]

            inp = self._prepare_digit(digit)
            if inp is None:
                continue

            pred = self.model.predict(inp, verbose=0)
            digit_class = int(np.argmax(pred))

            result += str(digit_class)

        if not result:
            print("[WARN] Цифры не найдены")

        return result if result else None