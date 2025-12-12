# Poppler Installation for Windows

`pdf2image` requires poppler-utils to be installed on your system.

## Windows Installation

1. **Download poppler for Windows:**
   - Go to: https://github.com/oschwartz10612/poppler-windows/releases
   - Download the latest release (e.g., `Release-XX.XX.X-X.zip`)

2. **Extract poppler:**
   - Extract to `C:\poppler` (or any location you prefer)
   - You should have folders like `bin`, `include`, `lib`, etc.

3. **Add to PATH (Option 1 - Recommended):**
   - Open System Properties → Environment Variables
   - Add `C:\poppler\Library\bin` to your PATH
   - Restart terminal/IDE

4. **Or use poppler_path parameter (Option 2):**
   - If you don't want to modify PATH, you can specify poppler_path in code:
   ```python
   from pdf2image import convert_from_path
   images = convert_from_path('file.pdf', poppler_path=r'C:\poppler\Library\bin')
   ```

## Verify Installation

```bash
# Check if poppler is in PATH
pdftoppm -h

# Or test with Python
python -c "from pdf2image import convert_from_path; print('OK')"
```

## Alternative: Use PyMuPDF (no poppler needed)

If you prefer not to install poppler, the code can fall back to PyMuPDF (fitz),
but for comprehensive mode, pdf2image is required as specified.

