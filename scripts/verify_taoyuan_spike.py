import pandas as pd
import re

# Load data
df = pd.read_csv("data/csv/building_ownership_trend.csv")

# Filter for Taoyuan City
taoyuan = df[df['city'] == '桃園市'].copy()

# Filter for recent periods (ROC 113Q1 onwards to see the trend)
# 2025 is 114, 2026 is 115
recent = taoyuan[taoyuan['period'] >= '113Q1'].sort_values('period')

# Calculate average area per unit (坪/棟)
recent['拍賣_平均單棟坪數'] = (recent['拍賣_坪數'] / recent['拍賣_棟數']).round(2)
recent['買賣_平均單棟坪數'] = (recent['買賣_坪數'] / recent['買賣_棟數']).round(2)

# Output relevant columns
print("桃園市近期拍賣與買賣數據對照：")
cols = ['period', '拍賣_棟數', '拍賣_坪數', '拍賣_平均單棟坪數', '買賣_平均單棟坪數']
print(recent[cols].to_string(index=False))

# Calculate historical baseline (excluding the suspected spike)
historical = taoyuan[taoyuan['period'] < '114Q1']
avg_historical_auction = (historical['拍賣_坪數'].sum() / historical['拍賣_棟數'].sum())
print(f"\n歷史平均單棟拍賣面積 (114Q1以前): {avg_historical_auction:.2f} 坪/棟")
