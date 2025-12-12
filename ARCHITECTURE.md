# PDF Parser Architecture - Implementation vs. SOTA Spec

Tämä dokumentti kartoittaa miten "state of the art" -speksi on toteutettu meidän konkreettisessa arkkitehtuurissa.

## Yleinen speksi vs. toteutus

### 1. "Tunnista ja eristä taulukkoalueet"

**Speksi:** Käytä visuaalista mallia (Table Transformer, DETR) tai konenäköheuristiikoita.

**Toteutus:**
- ✅ **PyMuPDF (fitz)** - Layout-esiprosessori
  - Tunnistaa taulukkoalueet `page.get_text("blocks")` -heuristiikalla
  - Eristää taulukot erillisiksi PNG-kuviksi (`crop_table_images`)
  - Tallentaa bounding boxit JSON-muotoon (`save_table_regions`)
  - **Sijainti:** `src/pymupdf_prepass.py`

**Status:** ✅ Toteutettu

---

### 2. "Tarkka OCR ja taulukkorakenne"

**Speksi:** PaddleOCR/PP-Structure, pdfplumber, docTR, tai hybridimalli.

**Toteutus:**
- ✅ **MinerU (magic-pdf)** - Pääparseri
  - State-of-the-art taulukoille
  - GPU-kiihdytetty (CUDA)
  - Palauttaa Markdown + JSON
  - **Sijainti:** `src/mineru_parser.py`

- ✅ **Docling** - Fallback parseri
  - OCR + layout-tunnistus
  - GPU-kiihdytetty
  - Suomenkielinen OCR-tuki
  - **Sijainti:** `src/docling_parser.py`

- ✅ **pdfplumber** - Tekstipohjaiset PDF:t
  - Nopea, ei GPU:ta tarvita
  - Säilyttää taulukkorakenteen
  - **Sijainti:** `src/pdfplumber_parser.py`

**Status:** ✅ Toteutettu (3 parseria)

**Tulevaisuudessa (valinnainen):**
- ⏳ PaddleOCR/PP-Structure - testattava yhdelle sivulle
- ⏳ docTR - kaksivaiheinen OCR

---

### 3. "Post-prosessi & kirjanpidon yhtälöt"

**Speksi:** Otsikkohierarkia, kirjanpidon yhtälöt, sanasto, numeromuodot.

**Toteutus:**
- ✅ **Tekstin normalisointi** - `src/text_cleanup.py`
  - Korjaa yhteen liimautuneet sanat (OCR-virheet)
  - Normalisoi numeromuodot
  - OCR-virheiden korjaus sanakirjalla

- ✅ **Taulukko-korjaukset** - `src/table_fixer.py`
  - Jakaa yhdistetyt numerosarakkeet
  - Rakentaa taulukot irrallisista label+numero -listoista
  - Poistaa duplikaatit

- ✅ **Kirjanpidon yhtälöt** - `src/validate_financials.py`
  - Validoi: `VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset`
  - Validoi: `VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA`
  - Validoi: `VASTAAVAA = PYSYVÄT VASTAAVAT + VAIHTUVAT VASTAAVAT`
  - **Ei korjaa automaattisesti** - vain logittaa virheet

**Status:** ✅ Toteutettu

---

### 4. "Ristiinvalidoi ja liputa epävarmat kohdat"

**Speksi:** Käytä kahta tai useampaa tekniikkaa ja vertaa tuloksia.

**Toteutus:**
- ✅ **Ristiinvalidoinnit** - `src/validation.py`
  - `compare_parsers()` - vertaa kahta parseria
  - `validate_accounting_equations()` - validoi kirjanpitokaavat
  - Pipeline-tuki: `validate_with_second_parser=True`

**Status:** ✅ Toteutettu

---

### 5. "Golden truth + unit testit"

**Speksi:** Laadi "kultainen totuus" taulu yhdestä taseesta ja kirjoita automaattiset yksikkötestit.

**Toteutus:**
- ✅ **Golden truth data** - `tests/test_parser.py`
  - Manuaalisesti varmennettu data Vesihuoltolaitoksen tasesta
  - JSON-muodossa: `GOLDEN_TRUTH` dict

- ✅ **Unit testit** - `tests/test_parser.py`
  - `test_vesihuolto_tase_golden_truth()` - vertaa parsittua dataa kultaan
  - `test_balance_sheet_equations()` - validoi kirjanpitokaavat
  - Automaattinen regressiotestaus

**Status:** ✅ Toteutettu

---

## Tietoisesti jätetty pois

### Pilvipalvelut (datan yksityisyys, kustannukset)

- ❌ **Adobe PDF Extract API** - Ei käytetä
- ❌ **AWS Textract** - Ei käytetä
- ❌ **Azure AI Document Intelligence** - Ei käytetä

**Syy:** Datan yksityisyys, kustannukset, vendor lock-in.

---

## Tulevaisuudessa (valinnainen)

### Transformer-mallit (tutkimus-/jatkokehitys)

- ⏳ **Donut (OCR-free)** - End-to-end transformer
- ⏳ **Pix2Struct** - Table image → HTML
- ⏳ **Table Transformer** - Taulukon lokalisointi

**Status:** Ei pakollisia Lapua v1:een, mutta hyviä ideoita jatkokehitykseen.

---

## Yhteenveto

| Speksin kohta | Toteutus | Status |
|---------------|----------|--------|
| Taulukkoalueiden tunnistus | PyMuPDF prepass | ✅ |
| OCR & taulukkorakenne | MinerU + Docling + pdfplumber | ✅ |
| Post-prosessi | text_cleanup.py + table_fixer.py | ✅ |
| Kirjanpidon yhtälöt | validate_financials.py | ✅ |
| Ristiinvalidoinnit | validation.py | ✅ |
| Golden truth testit | tests/test_parser.py | ✅ |
| Pilvipalvelut | Ei käytetä | ❌ (tietoinen valinta) |
| Transformer-mallit | Ei vielä | ⏳ (tulevaisuudessa) |

**Päätelmä:** Speksin keskeiset osat on toteutettu meidän stackillä (PyMuPDF + MinerU + Docling + post-prosessi). Laadun parantaminen tulee nyt kirjanpidon yhtälöistä ja automaattisista regressiotesteistä, ei parserin vaihtamisesta.

