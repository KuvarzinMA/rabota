from minio import Minio
from minio.error import S3Error


def main():
    # 1. Инициализация клиента
    # Замени данные на свои, если используешь не локальный сервер
    client = Minio(
        "10.2.1.50:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False  # Поставь True, если настроен HTTPS
    )

    bucket_name = "test-bucket"

    try:
        # 2. Создаем корзину, если она не существует
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print(f"Корзина '{bucket_name}' успешно создана.")
        else:
            print(f"Корзина '{bucket_name}' уже существует.")

        # 3. Загружаем файл на сервер
        # Файл 'test.txt' должен лежать рядом со скриптом
        source_file = "test.txt"
        destination_name = "uploaded_test.txt"

        client.fput_object(bucket_name, destination_name, source_file)
        print(f"Файл '{source_file}' успешно загружен как '{destination_name}'.")

        # 4. Скачиваем файл обратно под другим именем
        download_name = "downloaded_test.txt"
        client.fget_object(bucket_name, destination_name, download_name)
        print(f"Файл успешно скачан: '{download_name}'")

        client.r

    except S3Error as exc:
        print(f"Произошла ошибка: {exc}")


if __name__ == "__main__":
    main()