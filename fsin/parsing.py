import requests
from bs4 import BeautifulSoup
import re
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# ---------------------------
# 📦 регионы + slug (ВАЖНО!)
# ---------------------------
regions = {
    "Адыгея": "adygeya",
    "Алтайский край": "altayskiy-kray",
    "Амурская область": "amurskaya-oblast",
    "Архангельская область": "arkhangelskaya-oblast",
    "Башкортостан": "bashkortostan",
}

# ---------------------------
# 📞 нормализация
# ---------------------------
def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]

    if len(digits) == 10:
        digits = "7" + digits

    if len(digits) >= 11:
        return "+" + digits

    return None


def extract_phones(text):
    raw = re.findall(r'\+?\d[\d\-\(\)\s]{8,}', text)
    return list(set(filter(None, [normalize_phone(p) for p in raw])))


def extract_boss(text):
    for line in text.split("\n"):
        if "начальник" in line.lower():
            fio = re.findall(r'[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+', line)
            if fio:
                return fio[0]
    return None


# ---------------------------
# 🔎 ищем УФСИН на странице региона
# ---------------------------
def find_ufsin_link(region_slug):
    url = f"https://orgs.biz/{region_slug}/"

    r = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.select("a"):
        text = a.get_text(" ", strip=True)

        if "УФСИН" in text:
            href = a.get("href")
            if href:
                return "https://orgs.biz" + href

    return None


# ---------------------------
# 📄 парсим карточку
# ---------------------------
def parse_page(url):
    r = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")

    text = soup.get_text("\n")

    phones = extract_phones(text)
    boss = extract_boss(text)

    return phones, boss


# ---------------------------
# 🚀 main
# ---------------------------
def main():
    results = []

    for region, slug in regions.items():
        print(f"\n=== {region} ===")

        link = find_ufsin_link(slug)

        if not link:
            print("❌ не найден УФСИН")
            continue

        print("->", link)

        phones, boss = parse_page(link)

        results.append({
            "region": region,
            "phones": phones,
            "boss": boss
        })

        time.sleep(1)

    return results


if __name__ == "__main__":
    data = main()

    print("\n=== RESULT ===\n")

    for item in data:
        print(item)