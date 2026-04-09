import time
import random
import json
import re
import threading
import urllib3
from curl_cffi import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class FsinExpertParser:
    def __init__(self):
        self.impersonate = "chrome110"
        self.file = "fsin_validated_results.jsonl"
        self.lock = threading.Lock()
        with open(self.file, "w", encoding="utf-8") as f: pass

    def fetch(self, url):
        try:
            r = requests.get(url, impersonate=self.impersonate, timeout=20, verify=False, allow_redirects=True)
            if r.status_code == 200:
                html = r.content.decode(r.charset if r.charset else 'utf-8', errors='ignore')
                if 'windows-1251' in html.lower() or 'cp1251' in html.lower():
                    html = r.content.decode('cp1251', errors='ignore')
                return BeautifulSoup(html, "html.parser")
            return r.status_code
        except Exception:
            return None

    def norm(self, t):
        return re.sub(r"\s+", " ", t or "").strip()

    def is_real_fio(self, text):
        """Проверяет, является ли текст именем, а не названием организации"""
        stop_words = ['республик', 'управлен', 'федеральн', 'росси', 'край', 'область', 'гг', 'фсин', 'генерал',
                      'полковник']
        low_text = text.lower()
        if any(word in low_text for word in stop_words) and len(text.split()) > 4:
            return False
        # ФИО обычно состоит из 2-3 слов
        return 2 <= len(text.split()) <= 4

    def extract_boss(self, soup):
        if not soup or isinstance(soup, int): return "Не найдено"

        # Приоритет 1: Специфические классы (самый точный метод)
        target = soup.select_one('.management-name, .management-detail-title, .detail-title')
        if target:
            name = self.norm(target.get_text())
            if self.is_real_fio(name): return name

        # Приоритет 2: Поиск жирного текста (strong/b) после звания
        for rank in ['Начальник', 'Полковник', 'Генерал', 'Подполковник']:
            rank_node = soup.find(string=re.compile(rank, re.I))
            if rank_node:
                # Ищем в радиусе 3-х соседних элементов
                curr = rank_node.parent
                for _ in range(3):
                    if not curr: break
                    # Ищем внутри или в следующем элементе
                    for tag in ['strong', 'b', 'h3', 'h4']:
                        found = curr.find(tag) if curr.name != tag else curr
                        if found:
                            name = self.norm(found.get_text())
                            if self.is_real_fio(name): return name
                    curr = curr.next_sibling

        return "Не найдено"

    def extract_phone(self, soup):
        if not soup or isinstance(soup, int): return "Не найдено"
        text = self.norm(soup.get_text(" "))
        # Улучшенная регулярка для захвата кода города и полного номера
        pattern = r'(?:приемн|тел|дежурн).{0,50}(((?:\+7|8|7)[\s\-\(]{0,3}\d{3,5}[\s\-\)]{0,3}\d{1,3}[\s\-]{0,2}\d{2}[\s\-]{0,2}\d{2})|(?:\d{2,5}[\s\-]\d{2,3}[\s\-]\d{2}[\s\-]\d{2}))'
        match = re.search(pattern, text, re.I)
        return match.group(1) if match else "Не найдено"

    def parse_region(self, code):
        base = f"https://{code}.fsin.gov.ru"
        print(f"[*] Регион {code}...", end=" ", flush=True)

        # Пытаемся по разным путям, если 404
        paths = ["/management/", "/management/head.php", "/about/management/", "/"]
        final_soup = None

        for path in paths:
            res = self.fetch(base + path)
            if isinstance(res, BeautifulSoup):
                final_soup = res
                break
            elif res == 403:
                print("(403 Blocked)", end=" ")
                break

        boss = self.extract_boss(final_soup)

        # Для телефона проверяем страницу контактов, если не нашли на основной
        phone = self.extract_phone(final_soup)
        if phone == "Не найдено":
            contact_res = self.fetch(base + "/contact.php")
            if isinstance(contact_res, BeautifulSoup):
                phone = self.extract_phone(contact_res)

        result = {"region": code, "boss": boss, "phone": phone}

        with self.lock:
            with open(self.file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

        print(f"OK: {boss[:20]} | {phone}")

    def run(self):
        codes = [str(i).zfill(2) for i in range(1, 93)]
        for code in codes:
            self.parse_region(code)
            time.sleep(random.uniform(4, 7))  # Защита от 403 (увеличено)


if __name__ == "__main__":
    FsinExpertParser().run()