"""kio-orzeczenia-mcp - MCP server for KIO (Krajowa Izba Odwolawcza) rulings from orzeczenia.uzp.gov.pl."""

__version__ = "0.3.0"
__author__ = "MateMatic"
__license__ = "Apache-2.0"

USER_AGENT = f"matematic-kio-mcp/{__version__} (+https://matematic.co; kontakt@matematic.co)"
BASE_URL = "https://orzeczenia.uzp.gov.pl"

# Sciezki UZP - stan zweryfikowany 2026-07-31 (patrz DISCOVERY.md "Zmiana 2026-07").
# Wyszukiwarka jest AJAX: GET / oraz GET /Home/Search zwracaja tylko shell strony
# ("Wyszukiwanie dokumentow. Prosze czekac..."), wyniki dociagane sa POST-em na
# /Home/GetResults. Scraping MUSI uderzac w endpoint AJAX, nie w shell.
SEARCH_PATH = "/Home/GetResults"       # POST, form-urlencoded
DETAILS_PATH = "/Home/Details"         # GET  /Home/Details/{id}       - metryka
CONTENT_PATH = "/Home/ContentHtml"     # GET  /Home/ContentHtml/{id}   - pelna tresc (UWAGA: nie HtmlContent)
PDF_PATH = "/Home/PdfContent"          # GET  /Home/PdfContent/{id}    - PDF tresci
PDF_METRICS_PATH = "/Home/PdfMetrics"  # GET  /Home/PdfMetrics/{id}    - PDF metryki

# UZP zwraca sztywno 10 wynikow na strone (pole page-size nie jest wysylane w formularzu).
UZP_PAGE_SIZE = 10
