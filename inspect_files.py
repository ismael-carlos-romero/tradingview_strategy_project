import os
import sys
import pypdf
import openpyxl
import pandas as pd

def extract_pdf_to_txt(pdf_path, txt_path):
    print(f"Extracting PDF: {pdf_path} -> {txt_path}")
    if not os.path.exists(pdf_path):
        print(f"File {pdf_path} does not exist.")
        return
    
    reader = pypdf.PdfReader(pdf_path)
    num_pages = len(reader.pages)
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"=== PDF EXTRACTION: {pdf_path} ===\n")
        f.write(f"Total Pages: {num_pages}\n\n")
        
        for i in range(num_pages):
            f.write(f"--- Page {i + 1} ---\n")
            text = reader.pages[i].extract_text()
            f.write(text)
            f.write("\n\n")
    print(f"Done extracting {pdf_path}")

def inspect_excel_to_txt(excel_path, txt_path):
    print(f"Inspecting Excel: {excel_path} -> {txt_path}")
    if not os.path.exists(excel_path):
        print(f"File {excel_path} does not exist.")
        return
    
    xl = pd.ExcelFile(excel_path)
    sheet_names = xl.sheet_names
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"=== EXCEL INSPECTION: {excel_path} ===\n")
        f.write(f"Sheet Names: {sheet_names}\n\n")
        
        for sheet in sheet_names:
            f.write(f"\n=========================================\n")
            f.write(f"Sheet: {sheet}\n")
            f.write(f"=========================================\n")
            df = xl.parse(sheet)
            f.write(f"Shape: {df.shape}\n\n")
            f.write("Columns:\n")
            f.write(", ".join(map(str, df.columns)) + "\n\n")
            f.write("First 30 rows:\n")
            f.write(df.head(30).to_string())
            f.write("\n\n")
    print(f"Done inspecting {excel_path}")

if __name__ == "__main__":
    extract_pdf_to_txt("ESTRATEGIAS (1).pdf", "ESTRATEGIAS_extracted.txt")
    inspect_excel_to_txt("PROYECTO MELIORA OPCIONES FINANCIERAS.xlsx", "EXCEL_extracted.txt")
    print("All extraction complete.")
