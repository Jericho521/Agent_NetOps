import pandas as pd

path = r"C:\Users\Jericho\Desktop\网络告警事件级别表.xlsx"
df = pd.read_excel(path, sheet_name=None)
for k, v in df.items():
    print("=== SHEET:", k, "===")
    print(v.to_string())
    print()
