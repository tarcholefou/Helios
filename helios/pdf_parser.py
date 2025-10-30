import pdfplumber
import pandas as pd

def extract_tva_data(pdf_path: str):
    data = {"section": [], "designation": [], "quantité": [], "TTC": [], "TVA %": [], "TVA €": [], "HT": []}
    current_section = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text().split("\n")
            for line in text:
                # Repérer les sections
                if "OFFRES" in line:
                    current_section = "OFFRES"
                    continue
                elif "PRODUITS" in line:
                    current_section = "PRODUITS"
                    continue
                elif "TOTAUX" in line:
                    current_section = "TOTAUX"
                    continue

                # Extraire les lignes de données
                parts = line.split()
                if len(parts) >= 5 and any(c.isdigit() for c in parts[-1]):
                    try:
                        data["section"].append(current_section)
                        data["designation"].append(" ".join(parts[:-5]))
                        data["quantité"].append(parts[-5])
                        data["TTC"].append(parts[-4])
                        data["TVA %"].append(parts[-3])
                        data["TVA €"].append(parts[-2])
                        data["HT"].append(parts[-1])
                    except Exception:
                        pass

    df = pd.DataFrame(data)
    return df
