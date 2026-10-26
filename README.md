# Fitch Regulatory Filing Extractor (mock)

Streamlit app that "extracts" Solvency II QRT data from uploaded SFCR/QRT PDFs. Currently runs on
generated mock data (`mock_data.py`); no API key is needed.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
streamlit run app.py
```

- Templates: S.02.01.02, S.05.01.02, S.05.02.04, S.19.01.21, S.25.01 / S.25.05
- Dark/light toggle in the sidebar (dark by default)
- Mock data profile is picked from the file name and mirrors the sample filings:
  - `SFCR YE25` / `generali` – Generali Group SFCR (EUR thousand, partial internal model, S.xx templates)
  - `allianz` – Allianz Group SFCR (EUR thousand, group internal model, S.xx templates)
  - `axa` – AXA Insurance UK plc public QRTs (GBP whole pounds, PRA IR.xx templates, includes IR.19.01.21)
  - anything else – a generic sample group
- Group SFCRs do not contain S.19.01, so that tab shows "not included in this filing" for them
- To go live, replace `mock_data.extract()` with the OpenAI logic, keeping its return shape
  (`meta`, `templates`, `fields`).
