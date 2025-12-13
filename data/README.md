# Data Directory

Tämä kansio sisältää PDF-tiedostoja, joita käytetään parserin testaamiseen ja esimerkkeinä.

## Tiedostot

Lisää tähän kansioon PDF-tiedostoja, joita haluat parsia. Esimerkiksi:

- `Lapua-Tilinpaatos-2024.pdf`
- `Kauhava-Tilinpaatos-2024.pdf`
- `Seinäjoki-Tilinpaatos-2024.pdf`

## Huomio

- PDF-tiedostot eivät ole versionhallinnassa (`.gitignore` estää ne)
- Tämä on tarkoituksellista, koska PDF-tiedostot voivat olla suuria ja sisältää arkaluontoista tietoa
- Lisää omat PDF-tiedostosi tähän kansioon paikallisesti

## Käyttö

Kun olet lisännyt PDF-tiedoston tähän kansioon, voit parsia sen komennolla:

```bash
python -m src.cli data/oma-tiedosto.pdf -o out/oma-tiedosto
```

Tai comprehensive-moodilla:

```bash
python -m src.cli data/oma-tiedosto.pdf -o out/oma-tiedosto --comprehensive
```

## Esimerkkitiedostot

Jos haluat jakaa esimerkkitiedostoja muille käyttäjille, voit:

1. Lisätä ne tähän kansioon paikallisesti
2. Jakaa ne erillisellä tavalla (esim. Google Drive, Dropbox)
3. Tai jos tiedostot ovat julkisia, voit lisätä ne GitHub Releases -osiin
