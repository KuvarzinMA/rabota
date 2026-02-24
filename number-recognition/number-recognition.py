import cv2
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import os


def cv2_imshow(image):
    """Альтернатива cv2_imshow из Colab для локального использования"""
    # Конвертация BGR в RGB (так как OpenCV использует BGR, а matplotlib - RGB)
    if len(image.shape) == 3 and image.shape[2] == 3:
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        plt.imshow(image_rgb)
    else:
        # Для черно-белых изображений
        plt.imshow(image, cmap='gray')
    plt.axis('off')
    plt.show()


def run_recognition(image_path, model_path='postal_model.h5'):
    # 1. Загрузка модели
    if not os.path.exists(model_path):
        print(f"Модель {model_path} не найдена!")
        return

    model = tf.keras.models.load_model(model_path)

    # 2. Загружаем фото
    img = cv2.imread(image_path)
    if img is None:
        print("Файл не найден")
        return

    # 3. Принудительно отрезаем "шапку" (верхние 25% изображения)
    h_orig, w_orig = img.shape[:2]
    crop_top = int(h_orig * 0.25)
    img_cropped = img[crop_top:, :]

    # Сохраняем копию cropped изображения для отрисовки результата
    result_img = img_cropped.copy()
    gray = cv2.cvtColor(img_cropped, cv2.COLOR_BGR2GRAY)

    # 4. Улучшенная предобработка (Гауссово размытие + Пороговая обработка Оцу + Морфологические операции)

    # Применяем Гауссово размытие для уменьшения шума перед пороговой обработкой
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)  # Ядро 5x5, сигма 0
    print("Изображение после Гауссова размытия (blurred):")
    cv2_imshow(blurred)

    # Пороговая обработка Оцу: автоматически находит оптимальный порог
    # THRESH_BINARY_INV: чтобы цифры были белыми на черном фоне
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    print("Изображение после пороговой обработки Оцу (thresh):")
    cv2_imshow(thresh)

    # # Убираем пунктир и шум (MORPH_OPEN)
    # kernel = np.ones((3, 3), np.uint8)
    # clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    # print("Изображение после MORPH_OPEN (clean):")
    # cv2_imshow(clean)

    # --- Скелетизацию все еще не используем, так как обучающая выборка без нее ---
    # process_img = clean
    # --------------------------------------------------------------------------

    process_img = thresh  # Используем clean для поиска контуров.

    # 5. Сегментация (поиск цифр)
    contours, _ = cv2.findContours(process_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Отфильтровываем мелкий мусор и слишком большие объекты
        # Расширим диапазон размеров, чтобы не пропустить цифры, но отсечь явный мусор.
        # Аспектное соотношение 0.1 до 10.0 это очень широкий диапазон
        aspect_ratio = w / float(h)
        if 10 < h < 150 and 5 < w < 150 and 0.1 < aspect_ratio < 10.0:
            rects.append((x, y, w, h))

    # Сортируем контуры слева направо
    rects = sorted(rects, key=lambda r: r[0])

    full_index = ""
    print(f"Найдено объектов: {len(rects)}")
    if len(rects) != 11:
        print(
            f"ВНИМАНИЕ: Найдено {len(rects)} объектов, ожидалось 11. Возможно, есть ошибки сегментации. Покажу найденные объекты:")
        # Для отладки, если количество объектов не 10, покажем, что было найдено.
        for (x, y, w, h) in rects:
            cv2.rectangle(result_img, (x, y), (x + w, y + h), (0, 0, 255), 2)  # Красные рамки для некорректных
        cv2_imshow(result_img)
        return

    # 6. Распознавание каждой ячейки
    for i, (x, y, w, h) in enumerate(rects):
        # Вырезаем область цифры
        roi = process_img[y:y + h, x:x + w]

        # Центрирование цифры в квадрате 32x32 (как в датасете)
        final_roi = np.zeros((32, 32), dtype="uint8")
        scale = 20.0 / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        if new_w > 0 and new_h > 0:
            # Размещаем цифру в центре 32x32 изображения
            roi_res = cv2.resize(roi, (new_w, new_h))
            offset_x = (32 - new_w) // 2
            offset_y = (32 - new_h) // 2
            final_roi[offset_y:offset_y + new_h, offset_x:offset_x + new_w] = roi_res

        # Показываем, что видит модель для каждого ROI (для отладки)
        print(f"ROI {i + 1} перед предсказанием:")
        cv2_imshow(final_roi)

        # Нормализация для CNN
        roi_input = final_roi.astype("float32") / 255.0
        roi_input = np.expand_dims(roi_input, axis=-1)  # Превращаем в (32, 32, 1)
        roi_input = np.expand_dims(roi_input, axis=0)  # Добавляем размер батча (1, 32, 32, 1)

        # Предсказание
        prediction = model.predict(roi_input, verbose=0)
        digit = np.argmax(prediction)
        full_index += str(digit)

        # Рисуем рамку и число над ней на итоговом фото
        cv2.rectangle(result_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(result_img, str(digit), (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    # 7. Вывод результата
    print("-" * 30)
    print(f"РАСПОЗНАННЫЙ ТЕКСТ: {full_index}")
    print("-" * 30)
    cv2_imshow(result_img)


# --- ЗАПУСК ---
if __name__ == "__main__":
    # Просто замени название файла на свой
    image_file = 'numbers/img.png'

    # Проверяем существует ли файл
    if os.path.exists(image_file):
        run_recognition(image_file)
    else:
        print(f"Файл {image_file} не найден в текущей директории!")
        print(f"Текущая директория: {os.getcwd()}")
        print("Доступные файлы:")
        for file in os.listdir('.'):
            if file.endswith(('.png', '.jpg', '.jpeg')):
                print(f"  - {file}")