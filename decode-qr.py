import hashlib

def generate_md5_checksum(txt: str, secret: str) -> str:
    """Создаёт MD5 контрольную сумму для текста с секретом."""
    combined = txt + secret
    return hashlib.md5(combined.encode('utf-8')).hexdigest()


def verify_md5_checksum(full_text: str, secret: str, sep: str = ":") -> bool:
    """
    Проверяет контрольную сумму в строке вида 'data-<checksum>'.
    full_text: строка с данными и контрольной суммой
    secret: секрет для генерации хеша
    sep: разделитель между данными и хешем
    """
    parts = full_text.rsplit(sep, 1)
    if len(parts) != 2:
        return False  # нет контрольной суммы
    txt, given_checksum = parts
    calc_checksum = generate_md5_checksum(txt, secret)
    return calc_checksum == given_checksum

secret = ""
text_to_check = "ztmail:outgoing:1454585:43601135d7866cacecb0ba28d69c119e"

if verify_md5_checksum(text_to_check, secret):
    print("Контрольная сумма верна ✅")
else:
    print("Контрольная сумма НЕ совпадает ❌")
