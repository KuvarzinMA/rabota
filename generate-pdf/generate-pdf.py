from blank import create_blank as create_std
from rodstv import create_blank as create_filled


def generate_all(counter_start, prison_name, secret_key):
    """
    Пример функции, которая создает сразу оба типа бланков
    """

    # 1. Создаем обычный пустой бланк с QR-кодом
    print("Генерация бланка ответа...")
    create_std(
        counter=counter_start,
        secret=secret_key,
        prison=prison_name
    )

    # 2. Создаем заполненный (родственный) бланк
    print("Генерация заполненного бланка...")
    create_filled(
        counter=counter_start + 1,
        prison=prison_name,
        sender_fio="Иванов Иван Иванович",
        sender_bday="10.10.1985",
        recipient_fio="Петрова Мария Сергеевна",
        message_text="Привет! Это тестовое сообщение для проверки импорта."
    )


if __name__ == "__main__":
    PRISON = "СИЗО-100 УФСИН РОССИИ"
    SECRET = "top-secret-key"

    generate_all(1, PRISON, SECRET)