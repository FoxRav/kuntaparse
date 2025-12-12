## KÄYTTÖOHJE: PDF-tilinpäätösten parsinta (Markdown + JSON)

Tämä ohje kertoo miten prosessoit **yksittäisen PDF:n** (tai useita) omatoimisesti ja missä järjestyksessä pipeline tekee vaiheet.

### 1) Esivaatimukset (Windows)

#### 1.1 Virtuaaliympäristö

```powershell
cd F:\-DEV-\PDF_Parser
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### 1.2 Poppler (pdf2image)

`pdf2image` tarvitsee Popplerin. Varmista että Popplerin `bin` on PATH:ssa:

```powershell
$env:Path += ";C:\poppler\poppler-24.08.0\Library\bin"
```

#### 1.3 Suositellut env-muuttujat (Paddle/Windows)

```powershell
$env:DISABLE_MODEL_SOURCE_CHECK="True"
$env:HUGGINGFACE_HUB_DISABLE_OFFLINE="1"
$env:HF_HUB_OFFLINE="1"
$env:PYTHONIOENCODING="utf-8"
```

### 2) Suositus: aja aina “comprehensive” (koko dokumentti)

Tämä tuottaa **yhdestä tiedostosta** luettavan lopputuloksen:
- sivukuva (linkki)
- OCR-teksti lukujärjestyksessä (best-effort)
- taulukot (rakenteisena)
- validointi + low-confidence -raportti

```powershell
cd F:\-DEV-\PDF_Parser
.\.venv\Scripts\python.exe -m src.cli data\Lapua-Tilinpaatos-2024.pdf -o out\lapua_2024 --comprehensive
```

### 3) Debug: aja vain yksi sivu (nopea savutesti)

Kun haluat testata vain yhden PDF-sivun (1-indexed):

```powershell
.\.venv\Scripts\python.exe -m src.cli data\Lapua-Tilinpaatos-2024.pdf -o out\_smoke_p151 --comprehensive --comprehensive-start-page 151 --comprehensive-max-pages 1
```

Huom: tulostettu sivunumero ≠ PDF-sivu. Lapua-esimerkissä tulostettu sivu 150 = PDF-sivu 151.

### 4) Outputit (mitä syntyy)

Kun ajo on valmis, `out/<run>/` sisältää:
- `<pdf_nimi>.md`  
  Esim: `out/lapua_2024/Lapua-Tilinpaatos-2024.md`
- `<pdf_nimi>.tables.json`  
  Esim: `out/lapua_2024/Lapua-Tilinpaatos-2024.tables.json`
- `<pdf_nimi>.validation.json`  
  Esim: `out/lapua_2024/Lapua-Tilinpaatos-2024.validation.json`
- `work/` välituotokset:
  - `work/page_images/page_0001.png ...` (renderöidyt sivut)
  - `work/extracted_tables/*grid.png` (griddatut taulukkoalueet)
  - `work/progress.json` (checkpoint; päivittyy ajon aikana)

### 5) Prosessin sisäinen järjestys (mitä “scriptiä” ajetaan ja missä järjestyksessä)

Käytännössä sinun ei tarvitse ajaa erillisiä scriptejä käsin: **`src.cli` kutsuu `src.pipeline.process_pdf`** ja se hoitaa koko putken.

Comprehensive-moodissa järjestys on:

1. **PDF → rasterikuvat** (`pdf2image`)  
   - tuottaa `out/<run>/work/page_images/page_XXXX.png`
2. **Gridin piirtäminen** (OpenCV) + **PP-StructureV3** (PaddleOCR)  
   - tuottaa `out/<run>/work/extracted_tables/page_XXXX_table_Y_grid.png`
   - poimii taulut HTML/solurakenteena ja muuntaa Markdowniksi
3. **Postprocess** (domain-fixit)  
   - taseen 3-sarakkeinen rebuild (koordinaattipohjainen) vaikeille palstatauluille
4. **Deterministinen korjauspassi** (`src/repair_tables.py`)  
   - esim. `Saamiset = Myyntisaamiset + Muut saamiset` -yhtälöstä johdetut korjaukset
5. **OCR-tekstin siistintä** (dedup) (`src/ocr_dedup.py`)  
   - poistaa sivun OCR-teksteistä taulukon “numero-dumpit”, kun kanoninen taulukko on jo mukana
6. **Validointi** (`src/validate_financials.py`)  
   - yhtälövalidoinnit + low-confidence -solut `validation.json`iin
7. **Lopputiedostojen kirjoitus**  
   - `.md`, `.tables.json`, `.validation.json`

### 6) Seuranta (onko ajo jumissa vai eteneekö)

Renderöinti:

```powershell
$pages=(Get-ChildItem out\lapua_2024\work\page_images\*.png -ErrorAction SilentlyContinue).Count
"rendered_pages=$pages"
```

Taulukkovaihe (grid-kuvat kasvavat):

```powershell
$lastGrid=(Get-ChildItem out\lapua_2024\work\extracted_tables\*grid.png -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
"last_grid=$($lastGrid.Name) @ $($lastGrid.LastWriteTime)"
```

Checkpoint:

```powershell
Get-Content out\lapua_2024\work\progress.json
```

### 7) Nopea “onnistuiko vai ei” -tarkistus (sekunteja, ei OCR:ää)

```powershell
.\.venv\Scripts\python.exe -m src.quick_check out\lapua_2024
```

Tämä tarkistaa mm.:
- tiedostot löytyy
- `.md` sisältää 154 sivua (Lapua)
- tunnettu huono arvo (esim. `95 345 152,75`) ei esiinny
- taseen “Muut saamiset” on taulukossa järkevästi

### 8) Usean kaupungin ajaminen samalla prosessilla (vertailukelpoisuus)

```powershell
.\.venv\Scripts\python.exe -m src.cli data\Lapua-Tilinpaatos-2024.pdf -o out\lapua_2024 --comprehensive
.\.venv\Scripts\python.exe -m src.cli data\Kauhava-Tilinpaatos-2024.pdf -o out\kauhava_2024 --comprehensive
.\.venv\Scripts\python.exe -m src.cli data\Seinäjoki-Tilinpaatos-2024.pdf -o out\seinajoki_2024 --comprehensive
```

### 9) Jos ajo jää kesken

Yleisin seuraus on, että `work/page_images` ja `work/extracted_tables` sisältävät jo osan tuotoksista, mutta lopulliset `.md/.json` puuttuvat.

Toimi näin:

1. varmista ettei python-prosessi ole enää käynnissä
2. jos `out/<run>/.pdf_parser_run.lock` jäi jumiin, poista se
3. käynnistä sama komento uudestaan

```powershell
Remove-Item -Force out\lapua_2024\.pdf_parser_run.lock -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m src.cli data\Lapua-Tilinpaatos-2024.pdf -o out\lapua_2024 --comprehensive
```


