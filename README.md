# PDF to Markdown/JSON Parser (pdf2md)

PDF-parseri, joka muuntaa suomalaisten tilinpäätösten PDF:t LLM-ystävälliseen Markdown- ja JSON-muotoon.

English README: `README_EN.md`

Pääperiaatteet:
- Parsinta tehdään **aina PDF→rasteri (pdf2image)** -polulla silloin kun haetaan taulukkorakennetta (visuaalinen taulukkoparsinta).
- Taulukoiden luvut eivät saa muuttua (ei “keksittyjä” arvoja); epävarmat arvot merkitään ja raportoidaan.
- Kirjanpidon yhtälöillä tehdään automaattinen sanity-check ja virheet raportoidaan.

## Käyttöohje (askel-askeleelta)

Katso **`KÄYTTÖOHJE.md`**: siinä on tarkka ajosarja, seurantakomennot ja “fail fast” -tsekki.

## Arkkitehtuuri

**Workflow:**
1. **Comprehensive visual mode (`--comprehensive`)**:
   - Renderöi sivut kuviksi (`pdf2image`, tyypillisesti 300 DPI)
   - Piirtää “viivataulukon” (OpenCV) ja ajaa PaddleOCR **PP-StructureV3** -putken
   - Jälkikäsittelee tietyt vaikeat palstataulut koordinaattipohjaisesti 3-sarakkeiseksi (label/2024/2023)
2. **Standard mode (oletus)**:
   - PyMuPDF-esiprosessori: taulukkoalueiden heuristinen tunnistus + crop
   - MinerU/Docling/pdfplumber: parsinta + post-prosessointi (`table_fixer.py`, `text_cleanup.py`)
3. **Validointi**:
   - `validate_financials.py` kirjanpidon yhtälöillä
   - Low-confidence -solut merkitään `?` ja raportoidaan JSONiin

## Ominaisuudet

- **Layout-tunnistus**: PyMuPDF tunnistaa taulukkoalueet ennen parsintaa
- **Visuaalinen taulukkoparsinta**: PP-StructureV3 (PaddleOCR v3) + viivataulukon piirtäminen
- **Taulukot**: Domain-spesifiset korjaukset kunnallisille taseille ja palstataulukoille
- **Kirjanpitokaavat**: Automaattinen validointi ja virheiden liputus
- **Seuranta**: ajon etenemisen seuranta (renderöidyt sivut / grid-kuvat / taulukot)

## Asennus

```bash
# Luo virtuaaliympäristö
python -m venv .venv

# Aktivoi (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Aktivoi (Linux/Mac)
source .venv/bin/activate

# Asenna riippuvuudet
pip install -r requirements.txt
```

### Poppler (Windows, pdf2image)

`pdf2image` tarvitsee Popplerin. Katso `INSTALL_POPPLER.md` ja varmista että Popplerin `bin` on PATH:ssa, esim:

```powershell
# Example (adjust to your installation):
$env:Path += ";C:\poppler\Library\bin"
```

## GPU (suositus, jos mahdollista)

Jos koneessa on NVIDIA-GPU ja käytössä on Paddle CUDA-build, GPU on järkevä erityisesti `--comprehensive` / PP-Structure -ajossa.

- Tarkista ensin:
  - `nvidia-smi`
  - `python -c "import paddle; print(paddle.is_compiled_with_cuda(), paddle.get_device())"`

Jos `paddle.is_compiled_with_cuda()` on `False`, teillä on CPU-build ja PP-Structure käyttää CPU:ta vaikka GPU löytyisi.
Asenna silloin Paddle GPU -wheel, joka sopii teidän CUDA-ajuriin.

Huom: Paddle GPU wheelin tarkka asennuskomento riippuu Paddle:n julkaisemista Windows wheel-versioista (CUDA 12.x). Jos haluat, haen teille täsmäkomennon suoraan Paddle:n virallisesta asennusohjeesta ja lukitsen sen `requirements.txt` / `pyproject.toml` -tasolle.

## Käyttö

### CLI-komento

```bash
# Perusajo (MinerU oletuksena)
python -m src.cli data/Lapua-Tilinpaatos-2024.pdf -o out/lapua_2024

# Docling-parserilla
python -m src.cli data/Lapua-Tilinpaatos-2024.pdf -o out/lapua_2024 --use-docling

# CPU:lla (ei GPU)
python -m src.cli data/Lapua-Tilinpaatos-2024.pdf -o out/lapua_2024 --no-gpu

# Visuaalinen taulukkotunnistus yksittäisille sivuille (OpenCV + PP-StructureV3)
python -m src.cli data/Lapua-Tilinpaatos-2024.pdf -o out/lapua_2024 --visual-tables --visual-pages "151"

# Comprehensive mode (ALL pages) + optional debug limits
python -m src.cli data/Lapua-Tilinpaatos-2024.pdf -o out/lapua_2024 --comprehensive
python -m src.cli data/Lapua-Tilinpaatos-2024.pdf -o out/lapua_2024 --comprehensive --comprehensive-start-page 150 --comprehensive-max-pages 1
```

### Huom: tulostettu sivunumero vs PDF-sivu

Tilinpäätöksissä sivun oikean yläkulman numero (*tulostettu sivunumero*) ei välttämättä vastaa PDF:n sivuindeksiä.
Joissain aineistoissa tulostettu sivunumero on offsetissa PDF-sivuun nähden.

Tämän takia `--visual-pages` / `--comprehensive-start-page` pitää antaa PDF-sivuna (1-indexed).

### Python-API

```python
from pathlib import Path
from src.pipeline import process_pdf

pdf_path = Path("data/Lapua-Tilinpaatos-2024.pdf")
md_path = process_pdf(pdf_path, out_dir=Path("out/lapua_2024"))
print(f"Markdown: {md_path}")
```

## Output

Comprehensive-ajossa syntyy aina:
- `out/<run>/Lapua-Tilinpaatos-2024.md` (tai vastaava pdf-nimi)
- `out/<run>/Lapua-Tilinpaatos-2024.tables.json`
- `out/<run>/Lapua-Tilinpaatos-2024.validation.json`

`tables.json` sisältää taulukoille:
- `page`, `grid_image`, `html`, `markdown`
- `low_confidence_cells` (jos löytyy)

## Laadun varmistus (“100% onnistui”)

Automaattinen “onnistui/ei onnistunut” -tarkistus kannattaa tehdä näin:
- `*.tables.json` löytyy ja `total_tables > 0`
- `*.validation.json`:
  - `low_confidence.total_cells == 0` (tai vähintään tiedossa ja hyväksytty)
  - `validations.balance_sheet` ei sisällä virheitä (SUMMA VIRHE)

Huom: 100% tarkoittaa käytännössä “ei yhtään low-confidence -solua eikä yhtään kirjanpidon yhtälövirhettä”. Jos näitä löytyy, ne ovat listattu raporteissa.

## Esimerkkitapaus (ei pakollinen, mutta hyödyllinen)

Tilinpäätöksissä yleinen vaikea muoto on **palstataulukko ilman viivoja** (label + 2 vuotta), esim. kunnallisen liikelaitoksen tase.
Tätä varten projekti sisältää koordinaatti-/OCR-token -pohjaisen “3 sarakkeen rebuild” -polun.

## Prosessoi kaikki 3 kaupunkia samalla prosessilla (vertailukelpoisuus)

Suositus: käytä aina `--comprehensive`, jotta kaikki PDF:t käyvät saman polun läpi.

```powershell
cd <repo_root>
# Example (adjust to your installation):
$env:Path += ";C:\poppler\Library\bin"
$env:DISABLE_MODEL_SOURCE_CHECK="True"
$env:PYTHONIOENCODING="utf-8"

.\.venv\Scripts\python.exe -m src.cli data\city_a.pdf -o out\city_a_2024 --comprehensive
.\.venv\Scripts\python.exe -m src.cli data\city_b.pdf -o out\city_b_2024 --comprehensive
.\.venv\Scripts\python.exe -m src.cli data\city_c.pdf -o out\city_c_2024 --comprehensive
```

Jos haluat debugata yksittäistä ongelmasivua:
- `--comprehensive-start-page <pdf-sivu> --comprehensive-max-pages 1`

## Seuranta (PowerShell)

Kertatarkistus:

```powershell
$pwd | Out-Null  # run in repo root
$pages=(Get-ChildItem out\lapua_2024\work\page_images\*.png -ErrorAction SilentlyContinue).Count
$grids=(Get-ChildItem out\lapua_2024\work\extracted_tables\*grid.png -ErrorAction SilentlyContinue).Count
$json='out\lapua_2024\Lapua-Tilinpaatos-2024.tables.json'
if(Test-Path $json){$t=(Get-Content $json | ConvertFrom-Json); $total=$t.total_tables; $pp=$t.pages_processed}else{$total='(pending)'; $pp='(pending)'}
"rendered_pages=$pages grid_images=$grids pages_processed=$pp total_tables=$total"
```

Looppi 30s välein:

```powershell
for($i=0;$i -lt 200;$i++){
  $pages=(Get-ChildItem out\lapua_2024\work\page_images\*.png -ErrorAction SilentlyContinue).Count
  $grids=(Get-ChildItem out\lapua_2024\work\extracted_tables\*grid.png -ErrorAction SilentlyContinue).Count
  $json='out\lapua_2024\Lapua-Tilinpaatos-2024.tables.json'
  if(Test-Path $json){$t=(Get-Content $json | ConvertFrom-Json); $total=$t.total_tables; $pp=$t.pages_processed}else{$total='(pending)'; $pp='(pending)'}
  "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') rendered_pages=$pages grid_images=$grids pages_processed=$pp total_tables=$total"
  Start-Sleep -Seconds 30
}
```

## Parserivaihtoehdot

### Nykyiset parserit

1. **MinerU (magic-pdf)** - Oletus, state-of-the-art taulukoille
   - Hyvä: Monimutkaiset taulukot, yhdistetyt solut
   - GPU-kiihdytetty
   - Vaatii: CUDA-tuki

2. **Docling** - Fallback, OCR + layout-tunnistus
   - Hyvä: Skannatut PDF:t, suomenkielinen OCR
   - GPU-kiihdytetty
   - Vaatii: CUDA-tuki

3. **pdfplumber** - Tekstipohjaiset PDF:t
   - Hyvä: Natiivi-PDF:t, selkeät taulukkorajat
   - Nopea, ei GPU:ta tarvita
   - Rajoite: Ei toimi skannatuille PDF:ille

4. **PyMuPDF (fitz)** - Layout-tunnistus ja taulukkoalueiden eristys
   - Käytetään esiprosessointiin
   - Nopea koordinaattien poiminta

5. **Visuaalinen taulukkotunnistus (OpenCV + PP-StructureV3)** - Ongelmasivuille / comprehensive
   - Renderöi PDF-sivun kuvaksi
   - Piirtää viivat tekstilohkojen väliin (OpenCV)
   - Käyttää PaddleOCR:n **PP-StructureV3** -putkea taulukkorakenteen tunnistukseen
   - **Erityisen hyvä**: Palstataulukot ilman viivoja (esim. Vesihuoltolaitoksen tase)
   - Vaatii: `opencv-python-headless`, `pdf2image`, `paddleocr==3.3.2`, `paddlex[ocr]==3.3.11`
   - Aktivoidaan: `--visual-tables --visual-pages "<pdf-sivu>"` tai `--comprehensive`

### Suositellut lisäykset (tulevaisuudessa)

#### OCR- ja rakenneparsintatyökalut

1. **PaddleOCR + PP-Structure**
   ```bash
   pip install paddlepaddle paddleocr
   ```
   - Avoimen lähdekoodin OCR + taulukkorakenne
   - Palauttaa suoraan Markdown/JSON
   - Hyvä skannatuille PDF:ille
   - Vaatii: GPU suositeltu

2. **docTR**
   ```bash
   pip install python-doctr[torch]
   ```
   - Kaksivaiheinen OCR (detection + recognition)
   - Käyttövalmis, hyvä suorituskyky
   - Vaatii: GPU suositeltu

#### Pilvipalvelut (vaihtoehtoiset)

1. **Adobe PDF Extract API**
   - Purkaa tekstin ja rakenteen
   - Tunnistaa monimutkaiset taulukot
   - Palauttaa CSV/XLSX
   - Vaatii: API-avain, maksullinen

2. **AWS Textract**
   - ML-palvelu tekstin ja taulukoiden tunnistukseen
   - Automaattinen soluryhmittely
   - Vaatii: AWS-tili, maksullinen

3. **Azure AI Document Intelligence**
   - Poimii taulukot säilyttäen rakenteen
   - Luottamusarvot jokaiselle kentälle
   - Vaatii: Azure-tili, maksullinen

#### Transformer-mallit

1. **Donut (OCR-free)**
   - Transformer-pohjainen, ei erillistä OCR:ää
   - Hyvä tarkkuus
   - Vaatii: GPU, mallin lataus

2. **Pix2Struct**
   - Ottaa table-kuvan, tuottaa HTML-taulukon
   - Vaatii: Taulukon lokalisointi ensin (esim. Table Transformer)

## Ristiinvalidoinnit

Projekti tukee useiden parserien vertailua laadun varmistamiseksi:

```python
from src.validation import compare_parsers, validate_accounting_equations

# Vertaa kahta parseria
discrepancies = compare_parsers(
    parser1_text=md_text_mineru,
    parser2_text=md_text_docling,
    parser1_name="MinerU",
    parser2_name="Docling",
)

# Validoi kirjanpitokaavat
validations = validate_accounting_equations(md_text)
```

## Post-prosessointi

### Tekstin normalisointi (`text_cleanup.py`)

- Korjaa yhteen liimautuneet sanat (OCR-virheet)
- Normalisoi numeromuodot (tuhaterottimet, desimaalit)
- Korjaa yleiset OCR-virheet sanakirjalla

### Taulukko-korjaukset (`table_fixer.py`)

- Jakaa yhdistetyt numerosarakkeet
- Validoi kirjanpitokaavat:
  - `VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset`
  - `VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA`
- Korjaa automaattisesti ilmiselvät virheet
- Rakentaa taulukot irrallisista label+numero -listoista

### Otsikkohierarkia

Parseri säilyttää taseiden otsikkohierarkian:
- Ylätasot ilman numeroita (esim. "Oma pääoma", "Vieras pääoma")
- Alatasot numeroilla (esim. "Peruspääoma", "Edellisten tilikausien yli-/alijäämä")

## Output-rakenne

```
out/lapua_2024/
├── Lapua-Tilinpaatos-2024.md   # Lopullinen markdown (yksi tiedosto)
├── Lapua-Tilinpaatos-2024.tables.json
├── Lapua-Tilinpaatos-2024.validation.json
└── work/                        # Väliaikaistiedostot
    ├── extracted_tables/        # Griddatut taulukkoalueet (PNG)
    └── page_images/             # Renderöidyt sivut (PNG)
```

## Kehitys

### Testien ajo

```bash
pytest tests/ -v
```

### Tyyppitarkistus

```bash
mypy src/
```

### Koodin formatointi

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Projektirakenne

```
pdf2md/
├── src/
│   ├── __init__.py
│   ├── config.py              # Konfiguraatio
│   ├── pymupdf_prepass.py     # PyMuPDF layout-esiprosessori
│   ├── mineru_parser.py       # MinerU-parseri
│   ├── docling_parser.py      # Docling-parseri
│   ├── pdfplumber_parser.py   # pdfplumber-parseri (tekstipohjaiset PDF:t)
│   ├── marker_parser.py       # Marker-fallback
│   ├── pipeline.py            # Pääworkflow
│   ├── table_fixer.py         # Taulukko- ja tase-korjaukset
│   ├── text_cleanup.py        # Tekstin normalisointi
│   ├── html_table.py          # HTML->rows->Markdown (stdlib)
│   ├── ppstructure_postprocess.py # PPStructure token/koordinaatti -jälkikäsittely (tase 3-col)
│   ├── paddle_device.py       # GPU/CPU valinta Paddlelle (kun mahdollista)
│   ├── repair_tables.py       # Deterministiset, yhtälöistä johdetut korjaukset (ei arvaamista)
│   ├── ocr_dedup.py           # OCR-tekstin “taulukkodumppien” poisto kun taulukko on jo mukana
│   ├── quick_check.py         # Nopea post-run tarkistus (sekunteja, ei OCR:ää)
│   ├── validation.py          # Ristiinvalidoinnit
│   └── cli.py                 # CLI-rajapinta
├── tests/
│   ├── test_docling_parser.py
│   ├── test_marker_parser.py
│   └── test_pipeline.py
├── data/                      # PDF-tiedostot
│   ├── Lapua-Tilinpaatos-2024.pdf
│   ├── Kauhava-Tilinpaatos-2024.pdf
│   └── Seinäjoki-Tilinpaatos-2024.pdf
├── out/                       # Output (generoidaan ajon aikana)
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Tulevaisuuden parannukset

1. **Paddle GPU wheel Windowsille** - PP-StructureV3 GPU-kiihdytys käytännössä (paddle CUDA-build)
2. **docTR-tuki** - Kaksivaiheinen OCR
3. **Pilvipalvelu-vaihtoehdot** - Adobe/AWS/Azure API:t vertailupisteeksi
4. **Transformer-mallit** - Donut/Pix2Struct end-to-end -parsintaan
5. **Automaattiset testit** - "Kultainen totuus" -taulu yhdestä taseesta
6. **Batch-prosessointi** - Useiden PDF:ien käsittely kerralla

## Lisenssi

MIT
