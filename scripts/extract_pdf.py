"""提取澜起科技财报PDF文本"""
import pdfplumber
import sys

pdf_path = sys.argv[1] if len(sys.argv) > 1 else r'D:\投资\财报\澜起科技\澜起科技2025.pdf'
max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 15

with pdfplumber.open(pdf_path) as pdf:
    total = len(pdf.pages)
    print(f'总页数: {total}')
    for i in range(min(max_pages, total)):
        text = pdf.pages[i].extract_text() or ''
        print(f'\n=== 第{i+1}页 ===')
        print(text[:3000])
