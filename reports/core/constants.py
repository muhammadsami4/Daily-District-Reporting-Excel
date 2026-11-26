"""Static reference data, taken from the reference workbook
``25-11-2026_same_day_only.xlsx`` (sheet "Sheet1", 38 districts).

This module is framework independent. The database ``District`` and
``ReportCategory`` tables are seeded from these lists by
``python manage.py seed_master_data``; after that the database is the master list
(aliases can be edited in the Django admin).
"""

REFERENCE_SHEET_NAME = "Sheet1"
DATE_TEXT_FORMAT = "%d-%m-%Y"          # reference stores the date as text, e.g. '25-11-2026'
DATE_NUMBER_FORMAT = "dd-mm-yyyy"      # number format applied to the date cells in the reference
FIXED_COLUMNS = ("Sr", "District", "Date")

# Column widths copied from the reference workbook (column A is left at default).
COLUMN_WIDTHS = {
    "B": 17.109375, "C": 16.44140625, "D": 12.109375, "E": 13.6640625,
    "F": 12.88671875, "G": 29.5546875, "H": 18.33203125, "I": 20.0,
}
HEADER_FILL_RGB = "FF228B22"           # green header fill used by the reference

# code, label shown in the web app, header in Excel (spelling kept exactly as in the reference)
CATEGORIES = [
    {"code": "added", "label": "Located", "excel_header": "added",
     "aliases": ["Located Total", "Located", "Added"], "mapping_confirmed": True},
    {"code": "released", "label": "Released", "excel_header": "Released",
     "aliases": ["Released Total"], "mapping_confirmed": True},
    {"code": "deported", "label": "Deported", "excel_header": "deported",
     "aliases": ["Deported Total"], "mapping_confirmed": True},
    {"code": "under_process", "label": "Under Process", "excel_header": "DEPORATEDION UNDER PROCESS",
     "aliases": ["UnderProcess", "Under Process", "Deportation Under Process"], "mapping_confirmed": True},
    {"code": "returned", "label": "Returned", "excel_header": "Retuned",
     "aliases": ["Returned Total", "Retuned"], "mapping_confirmed": True},
    # The brief asked for this mapping to be confirmed before finalising.
    {"code": "arrested_lea", "label": "Taken by LEA", "excel_header": "Arrested by LEA",
     "aliases": ["Taken by LEA", "Taken by L.E.A", "Arrested by LEA", "LEA"], "mapping_confirmed": False},
]

# Name and extra spellings. ORDER IS THE REFERENCE ORDER - do not sort.
DISTRICTS = [
    ("Attock", []),
    ("Bahawalnagar", ["Bahawal Nagar"]),
    ("Bahawalpur", []),
    ("Bhakkar", []),
    ("Chakwal", []),
    ("Chiniot", []),
    ("Dera Ghazi Khan", ["D.G. Khan", "DG Khan", "D G Khan", "DGK"]),
    ("Faisalabad", []),
    ("Gujranwala", []),
    ("Gujrat", []),
    ("Hafizabad", []),
    ("Jhang", []),
    ("Jhelum", ["Jehlum", "Jhelam"]),
    ("Kasur", []),
    ("Khanewal", []),
    ("Khushab", []),
    ("Kot Addu", ["Kot Adu", "Kotadu"]),
    ("Lahore", []),
    ("Layyah", ["Leiah", "Layya"]),
    ("Lodhran", []),
    ("Mandi Bahauddin", ["Mandi Bahaudin", "M.B. Din", "MB Din"]),
    ("Mianwali", []),
    ("Multan", []),
    ("Muree", ["Murree"]),
    ("Muzaffargarh", ["Muzaffar Garh"]),
    ("Nankana Sahib", ["Nankana"]),
    ("Narowal", []),
    ("Okara", []),
    ("Pakpattan", ["Pak Pattan"]),
    ("Rahim Yar Khan", ["R.Y. Khan", "RY Khan", "RYK"]),
    ("Rajanpur", ["Rajan Pur"]),
    ("Rawalpindi", ["Rawal Pindi", "Rwp"]),
    ("Sahiwal", []),
    ("Sargodha", []),
    ("Sheikhupura", ["Sheikhu Pura", "Shaikhupura", "Sheikhopura"]),
    ("Sialkot", []),
    ("Toba Tek Singh", ["T.T.Singh", "T.T. Singh", "TT Singh", "TTS"]),
    ("Vehari", []),
]
