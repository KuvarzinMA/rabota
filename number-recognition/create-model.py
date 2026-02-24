import tensorflow as tf
from tensorflow.keras import layers, models
DATASET_DIR = "postal_dataset_v2"
# Загрузка и перемешивание
train_ds = tf.keras.utils.image_dataset_from_directory(
    DATASET_DIR, validation_split=0.2, subset="training", seed=42,
    image_size=(32, 32), batch_size=32, color_mode='grayscale'
)
val_ds = tf.keras.utils.image_dataset_from_directory(
    DATASET_DIR, validation_split=0.2, subset="validation", seed=42,
    image_size=(32, 32), batch_size=32, color_mode='grayscale'
)

# Перемасштабирование
train_ds = train_ds.map(lambda x, y: (x / 255.0, y))
val_ds = val_ds.map(lambda x, y: (x / 255.0, y))

model = models.Sequential([
    layers.Conv2D(32, (3, 3), activation='relu', input_shape=(32, 32, 1)),
    layers.MaxPooling2D((2, 2)),
    layers.Conv2D(64, (3, 3), activation='relu'),
    layers.MaxPooling2D((2, 2)),
    layers.Flatten(),
    layers.Dense(128, activation='relu'),
    layers.Dropout(0.5),
    layers.Dense(10, activation='softmax')
])

model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])

# Останавливаемся вовремя, чтобы не переучить
callback = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=3)

model.fit(train_ds, validation_data=val_ds, epochs=20, callbacks=[callback])
model.save('postal_model.h5')
print("Model trained and saved as postal_model.h5")