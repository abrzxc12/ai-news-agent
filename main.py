import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import markdown2
import requests

# Biblioteki zewnętrzne
import feedparser
from groq import Groq
from dotenv import load_dotenv

# 1. Ładowanie zmiennych z pliku .env
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Lista źródeł RSS
RSS_URLS = [
    "https://wiadomosci.onet.pl/.feed",
    "https://feeds.feedburner.com/niebezpiecznik/",
    "https://techcrunch.com/feed/",
    "https://naekranie.pl/feed/news.xml",
    "https://feeds.macrumors.com/MacRumors-All"
    
]


MY_LAT = 53.12
MY_LON = 18.00

def get_weather_data(lat, lon):
    """Pobiera aktualną pogodę z OpenWeatherMap"""
    print("🌤️ Pobieram dane z OpenWeatherMap...")
    
    if not OPENWEATHER_API_KEY:
        return "⚠️ Brak klucza API OpenWeather w pliku .env"

    # units=metric (Celsjusz), lang=pl (polski opis)
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=pl"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if response.status_code != 200:
            return f"Błąd API pogody: {data.get('message', 'Nieznany błąd')}"

        description = data['weather'][0]['description']
        temp = round(data['main']['temp'], 1)
        feels_like = round(data['main']['feels_like'], 1)
        humidity = data['main']['humidity']
        wind_speed = data['wind']['speed']
        city = data.get('name', 'Twoja lokalizacja')
        
        return f"""
        MIASTO: {city}
        OPIS: {description.capitalize()}
        TEMP: {temp}°C (Odczuwalna: {feels_like}°C)
        WILGOTNOŚĆ: {humidity}%
        WIATR: {wind_speed} m/s
        """
    except Exception as e:
        print(f"❌ Błąd pobierania pogody: {e}")
        return "Brak danych pogodowych (błąd połączenia)."

def get_news_from_rss():
    # Pobiera newsy z listy RSS i łączy w jeden tekst
    combined_text = ""
    print("📰 Pobieram newsy z RSS...")

    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
        # Bierzemy tylko 5 najnowszych z każdego źródła, żeby nie zapchać modelu
            for entry in feed.entries[:4]:
                clean_title = entry.title
                clean_link = entry.link
            # Niektóre RSS nie mają opisu, więc się zabezpieczamy
                clean_desc = entry.description if 'description' in entry else "Brak opisu"
                combined_text += f"TYTUŁ: {clean_title}\nOPIS: {clean_desc}\nLINK: {clean_link}\n---\n"
        except Exception as e:
            print(f"⚠️ Błąd przy pobieraniu RSS {url}: {e}")

    return combined_text

def summarize_with_groq(news_data, weather_data):
    # Wysyła dane do Groq celem streszczenia
    print("🧠 Analizuję dane przy użyciu Groq (Llama 3)...")

    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""
    Jesteś polskim redaktorem naczelnym newslettera. Twoi czytelnicy nie znają angielskiego.
    
    TWOJE ZADANIE:
    Przetłumacz i streść dostarczone newsy

    ⛔ ZAKAZY (BARDZO WAŻNE):
    1. NIE WOLNO Ci zostawić żadnego tytułu po angielsku.
    2. NIE CYTUJ oryginalnych nagłówków.
    3. Nie zaczynaj zdania od "Artykuł omawia..." - przejdź do rzeczy.

    INSTRUKCJE DO TYTUŁÓW:
    - Każdy tytuł musi być przetłumaczony na język polski.
    - Jeśli tytuł jest trudny do przetłumaczenia, wymyśl nowy, chwytliwy polski nagłówek oddający sens newsa.
    - Przykład: Zamiast "SpaceX launches Starship", napisz "**SpaceX wystrzelił statek Starship**".

    KRYTYCZNE ZASADY JĘZYKOWE:
    1. **CAŁOŚĆ MUSI BYĆ PO POLSKU.** To jest najważniejsza zasada.
    2. Jeśli źródłowy news jest po angielsku, niemiecku lub w innym języku -> **PRZETŁUMACZ GO NA POLSKI**.
    3. Tytuły sekcji i nagłówki newsów również muszą być po polsku.
    
    STRUKTURA MAILA:
    1. **🌤️ Sekcja Pogodowa**: Krótko i po ludzku (jak się ubrać).
    2. **🚀 Przegląd Newsów**:
       - Wybierz 5-7 najważniejszych newsów.
       - Ignoruj duplikaty.
       - Podziel na kategorie (np. Świat, Tech, Polska, Kino, Bezpieczeństwo).
       - Format: **Polski Tytuł**
       - Opis: 1-2 zdania streszczenia po polsku.
       - Na końcu każdego newsa dodaj link w formacie Markdown: [Link](link).
    3. **💡 Cytat dnia**: Inspirująca myśl.
    
    DANE WEJŚCIOWE:
    === POGODA ===
    {weather_data}
    
    === NEWSY ===
    {news_data}
    """

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Jesteś pomocnym asystentem AI. Zawsze odpowiadasz w języku polskim, niezależnie od języka danych wejściowych."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.6,
    )

    return completion.choices[0].message.content


def send_email(markdown_content):
    """Konwertuje Markdown na HTML i wysyła email"""
    print("📧 Generuję i wysyłam email...")
    
    # 1. Konwersja Markdown -> HTML
    html_content = markdown2.markdown(markdown_content)
    
    # 2. Szablon HTML (CSS w środku)
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f9; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); padding: 30px 20px; text-align: center; color: white; }}
            .header h1 {{ margin: 0; font-size: 28px; letter-spacing: 1px; }}
            .header p {{ margin: 5px 0 0; opacity: 0.9; font-size: 14px; }}
            .content {{ padding: 30px; color: #333; line-height: 1.6; }}
            h1, h2, h3 {{ color: #2c3e50; margin-top: 25px; border-bottom: 2px solid #f0f0f0; padding-bottom: 8px; }}
            a {{ color: #007bff; text-decoration: none; font-weight: bold; }}
            a:hover {{ text-decoration: underline; }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 10px; }}
            .footer {{ background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #888; border-top: 1px solid #eee; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>AI Daily Brief</h1>
                <p>{datetime.now().strftime('%A, %d %B %Y')}</p>
            </div>
            <div class="content">
                {html_content}
            </div>
            <div class="footer">
                <p>Wygenerowano automatycznie: Python + Groq + OpenWeather</p>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = f"☕ Twoja Prasówka - {datetime.now().strftime('%d.%m')}"
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    try:
        # Łączenie przez port 587 (STARTTLS) - omija większość blokad
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Email wysłany pomyślnie!")
    except Exception as e:
        print(f"❌ Błąd wysyłania emaila: {e}")


def main():
    print("--- START AGENTA ---")
    
    # 1. Dane
    weather = get_weather_data(MY_LAT, MY_LON)
    news = get_news_from_rss()
    
    if not news and "Brak danych" in weather:
        print("Brak danych do wysłania. Kończę.")
        return

    # 2. Przetwarzanie (AI)
    ai_summary = summarize_with_groq(news, weather)
    
    # 3. Wysyłka
    send_email(ai_summary)
    
    print("--- KONIEC ---")

if __name__ == "__main__":
    main()