import asyncio
from nicegui import ui
import httpx
from selectolax.parser import HTMLParser
import urllib.parse
import random
import os

# Debug-Modus schalten
DEBUG_MODE = True  # Auf False setzen, wenn nicht debuggt werden soll

def save_debug_html(html_content: str):
    """Speichert den HTML-Response in einer Datei, falls DEBUG_MODE aktiviert ist."""
    if DEBUG_MODE:
        debug_file = 'debug.html'
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Debug: HTML-Response wurde in '{debug_file}' gespeichert.")

def extract_text(node, default='Nicht verfügbar'):
    return node.text(strip=True) if node else default

def parse_price(price_text):
    """Extrahiert den Preis aus dem Text und gibt ihn als Float zurück."""
    if not price_text:
        return float('inf')  # Kein Preis angegeben
    price_text = price_text.lower()
    if 'vb' in price_text:  # Verhandlungsbasis
        return float('inf')
    if 'zu verschenken' in price_text:  # Gratis
        return 0.0
    if 'auf anfrage' in price_text:  # Preis auf Anfrage
        return float('inf')
    # Entferne alle nicht-numerischen Zeichen (außer Komma und Punkt)
    price_text = ''.join(c for c in price_text if c.isdigit() or c in {',', '.'})
    # Ersetze Komma durch Punkt für die Float-Konvertierung
    price_text = price_text.replace(',', '.')
    try:
        return float(price_text)
    except ValueError:
        return float('inf')  # Falls die Konvertierung fehlschlägt

async def scrape_kleinanzeigen(search_term, location, min_price, max_price, sort_by, results_container, loading_spinner, exclude_words, radius):
    loading_spinner.set_visibility(True)
    results_container.clear()

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36'
    ]

    try:
        base_url = 'https://www.kleinanzeigen.de/s-suchanfrage.html'
        params = {'keywords': search_term, 'locationStr': location}
        if min_price and max_price:
            params['minPrice'] = min_price
            params['maxPrice'] = max_price
        if radius:
            params['radius'] = radius  # Umkreis in Kilometern
        full_url = f'{base_url}?{urllib.parse.urlencode(params)}'

        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.kleinanzeigen.de/'
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(10.0)) as client:
            await asyncio.sleep(random.uniform(1, 3))
            response = await client.get(full_url, headers=headers)
            if response.status_code != 200:
                ui.notify(f'Fehler beim Abrufen der Seite: {response.status_code}', type='negative')
                return

            save_debug_html(response.text)

            parser = HTMLParser(response.text)
            ads = parser.css('article.aditem')
            results = []

            for ad in ads:
                try:
                    title_node = ad.css_first('h2.text-module-begin a')
                    title = extract_text(title_node, 'Kein Titel')
                    link = f"https://www.kleinanzeigen.de{title_node.attributes['href']}" if title_node and 'href' in title_node.attributes else '#'
                    
                    # Preis-Extraktion
                    price_node = ad.css_first('p.aditem-main--middle--price-shipping--price')
                    price_text = extract_text(price_node, 'Preis auf Anfrage')
                    
                    date_node = ad.css_first('div.aditem-main--top--right')
                    location_node = ad.css_first('div.aditem-main--top--left')

                    # Überprüfen, ob der Titel ausgeschlossene Wörter enthält
                    if exclude_words and any(word.lower() in title.lower() for word in exclude_words):
                        continue  # Überspringe diese Anzeige

                    results.append({
                        'title': title,
                        'price_text': price_text,
                        'link': link,
                        'date': extract_text(date_node),
                        'location': extract_text(location_node)
                    })
                except Exception as e:
                    print(f"Fehler beim Parsen einer Anzeige: {e}")

            # Sortierung nach Preis (optional, falls numerisch interpretierbar)
            try:
                for r in results:
                    # Versuchen, den Preis als Zahl zu parsen; wenn das fehlschlägt, wird ein sehr hoher Preis angenommen
                    try:
                        r['price'] = float(r['price_text'].replace('€', '').replace('.', '').replace(',', '.').strip() or 'inf')
                    except ValueError:
                        r['price'] = float('inf')  # Setze den Preis auf unendlich, wenn er nicht geparst werden kann
            except Exception as e:
                print(f"Fehler beim Parsen des Preises: {e}")

            if sort_by == 'Preis aufsteigend':
                results.sort(key=lambda x: x['price'])
            elif sort_by == 'Preis absteigend':
                results.sort(key=lambda x: x['price'], reverse=True)

            ui.notify(f'{len(results)} Ergebnisse gefunden', type='positive')
            results_container.clear()

            if not results:
                ui.label('Keine Ergebnisse gefunden').classes('text-lg text-gray-500 my-4')
                return

            with results_container:
                with ui.grid(columns=2).classes('gap-4 p-4'):
                    for result in results:
                        with ui.card().classes('w-full'):
                            with ui.column().classes('gap-2'):
                                ui.label(result['title']).classes('text-lg font-bold text-blue-600 break-words')
                                with ui.row().classes('justify-between items-center'):
                                    ui.label(result['price_text']).classes('text-xl font-bold text-green-600')
                                    ui.label(result['date']).classes('text-sm text-gray-500')
                                ui.label(result['location']).classes('text-sm text-gray-600')
                                ui.link('Zur Anzeige', result['link']).classes('text-blue-500 hover:text-blue-700')
    except httpx.HTTPStatusError as e:
        ui.notify(f'HTTP-Fehler: {e}', type='negative')
    except httpx.RequestError as e:
        ui.notify(f'Netzwerkfehler: {e}', type='negative')
    except Exception as e:
        ui.notify(f'Unerwarteter Fehler: {str(e)}', type='negative')
    finally:
        loading_spinner.set_visibility(False)

# NiceGUI-Interface
ui.dark_mode().enable()

with ui.card().classes('w-full max-w-3xl mx-auto my-4 p-4'):
    ui.label('Kleinanzeigen-Suche').classes('text-2xl font-bold mb-4 text-center')

    with ui.column().classes('w-full gap-4'):
        with ui.row().classes('w-full gap-4'):
            search_input = ui.input(label='Suchbegriff', placeholder='z.B. iPhone, Fahrrad...').classes('w-full')
            location_input = ui.input(label='Ort', placeholder='z.B. Berlin, Hamburg...').classes('w-full')
        with ui.row().classes('w-full gap-4'):
            min_price_input = ui.number(label='Mindestpreis (€)', placeholder='0').classes('w-full')
            max_price_input = ui.number(label='Maximalpreis (€)', placeholder='1000').classes('w-full')
        with ui.row().classes('w-full gap-4'):
            exclude_input = ui.input(label='Ausschließen (Wörter, durch Komma getrennt)', placeholder='z.B. defekt, kaputt').classes('w-full')
            radius_input = ui.number(label='Umkreis (km)', placeholder='z.B. 10').classes('w-full')
        sort_select = ui.select(['Preis aufsteigend', 'Preis absteigend'], label='Sortierung', value='Preis aufsteigend').classes('w-full')
        
        loading_spinner = ui.spinner('dots').classes('text-4xl text-blue-500 mx-auto my-4')
        loading_spinner.set_visibility(False)
        
        results_container = ui.column().classes('w-full mt-4')

        async def search_callback():
            exclude_words = [word.strip() for word in exclude_input.value.split(',')] if exclude_input.value else []
            radius = radius_input.value if radius_input.value else None
            await scrape_kleinanzeigen(
                search_input.value,
                location_input.value,
                min_price_input.value,
                max_price_input.value,
                sort_select.value,
                results_container,
                loading_spinner,
                exclude_words,
                radius
            )

        ui.button('Suchen', on_click=search_callback).classes('w-full bg-blue-500 hover:bg-blue-700 text-white')

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='Kleinanzeigen-Suche', dark=True)