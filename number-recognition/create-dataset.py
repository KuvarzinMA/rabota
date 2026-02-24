import os
import random
import shutil
import numpy as np
import cv2

# ==============================
# CONFIG
# ==============================

DATASET_DIR = "postal_dataset_v2"
IMG_SIZE = 32
SAMPLES_PER_CLASS = 4000

# Твои сегментные пути
PATHS = {
    0: [(0,2), (2,8), (8,6), (6,0)],
    1: [(3,2), (2,8)],
    2: [(0,2), (2,5), (5,6), (6,8)],
    3: [(0,2), (2,3), (3,5), (5,6)],
    4: [(0,3), (3,5), (2,8)],
    5: [(2,0), (0,3), (3,5), (5,8), (8,6)],
    6: [(2,3), (3,6), (6,8), (8,5), (5,3)],
    7: [(0,2), (2,3), (3,6)],
    8: [(0,2), (2,8), (8,6), (6,0), (3,5)],
    9: [(0,2), (0,3), (3,5), (5,2), (5,6)]
}

# ==============================
# UTILS
# ==============================

def elastic_distortion(img, alpha=2, sigma=6):
    dx = np.random.randn(IMG_SIZE, IMG_SIZE)
    dy = np.random.randn(IMG_SIZE, IMG_SIZE)

    dx = cv2.GaussianBlur(dx, (17,17), sigma) * alpha
    dy = cv2.GaussianBlur(dy, (17,17), sigma) * alpha

    x, y = np.meshgrid(np.arange(IMG_SIZE), np.arange(IMG_SIZE))
    map_x = (x + dx).astype(np.float32)
    map_y = (y + dy).astype(np.float32)

    return cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def perspective_transform(img):
    margin = random.randint(0, 4)
    pts1 = np.float32([[0,0],[IMG_SIZE,0],[0,IMG_SIZE],[IMG_SIZE,IMG_SIZE]])
    pts2 = np.float32([
        [random.randint(0, margin), random.randint(0, margin)],
        [IMG_SIZE-random.randint(0, margin), random.randint(0, margin)],
        [random.randint(0, margin), IMG_SIZE-random.randint(0, margin)],
        [IMG_SIZE-random.randint(0, margin), IMG_SIZE-random.randint(0, margin)]
    ])
    M = cv2.getPerspectiveTransform(pts1, pts2)
    return cv2.warpPerspective(img, M, (IMG_SIZE, IMG_SIZE))


def random_breaks(img):
    for _ in range(random.randint(0,3)):
        x = random.randint(0, IMG_SIZE-3)
        y = random.randint(0, IMG_SIZE-3)
        w = random.randint(1,3)
        h = random.randint(1,3)
        img[y:y+h, x:x+w] = img[y:y+h, x:x+w] * random.uniform(0,0.4)
    return img


def variable_thickness_line(img, p1, p2):
    thickness = random.randint(1,4)
    cv2.line(img, p1, p2, 255, thickness)

    # локальное утолщение
    if random.random() < 0.5:
        mid = ((p1[0]+p2[0])//2, (p1[1]+p2[1])//2)
        cv2.circle(img, mid, random.randint(1,3), 255, -1)


def curved_line(img, p1, p2):
    mid = (
        (p1[0]+p2[0])//2 + random.randint(-3,3),
        (p1[1]+p2[1])//2 + random.randint(-3,3)
    )
    pts = np.array([p1, mid, p2], np.int32)
    cv2.polylines(img, [pts], False, 255, random.randint(1,3))


# ==============================
# DATASET GENERATION
# ==============================

def generate_dataset():

    if os.path.exists(DATASET_DIR):
        shutil.rmtree(DATASET_DIR)

    for i in range(10):
        os.makedirs(os.path.join(DATASET_DIR, str(i)))

    for digit, lines in PATHS.items():
        for s in range(SAMPLES_PER_CLASS):

            # фон не идеально чёрный
            img = np.ones((IMG_SIZE, IMG_SIZE), dtype=np.uint8) * random.randint(0, 30)

            padding = random.randint(4, 8)
            w = IMG_SIZE - 2*padding
            h = IMG_SIZE - 2*padding

            pts = [
                (padding, padding),
                (padding+w//2, padding),
                (padding+w, padding),
                (padding, padding+h//2),
                (padding+w//2, padding+h//2),
                (padding+w, padding+h//2),
                (padding, padding+h),
                (padding+w//2, padding+h),
                (padding+w, padding+h)
            ]

            # jitter
            jitter = random.randint(0,4)
            pts = [(x+random.randint(-jitter,jitter),
                    y+random.randint(-jitter,jitter)) for x,y in pts]

            # рисуем линии
            for start, end in lines:

                if random.random() < 0.4:
                    curved_line(img, pts[start], pts[end])
                else:
                    variable_thickness_line(img, pts[start], pts[end])

            # аугментации
            if random.random() < 0.7:
                angle = random.uniform(-25,25)
                M = cv2.getRotationMatrix2D((IMG_SIZE//2, IMG_SIZE//2), angle, 1)
                img = cv2.warpAffine(img, M, (IMG_SIZE, IMG_SIZE))

            if random.random() < 0.6:
                img = perspective_transform(img)

            if random.random() < 0.7:
                img = elastic_distortion(img)

            if random.random() < 0.8:
                img = cv2.GaussianBlur(img, random.choice([(3,3),(5,5)]), 0)

            img = random_breaks(img)

            # шум
            noise = np.random.normal(0, 10, (IMG_SIZE, IMG_SIZE))
            img = np.clip(img + noise, 0, 255).astype(np.uint8)

            cv2.imwrite(os.path.join(DATASET_DIR, str(digit), f"{s}.png"), img)

    print("Dataset v2 готов.")


generate_dataset()