import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model
from datetime import datetime, timedelta
import re
import os

# --- 頁面配置 ---
st.set_page_config(page_title="百貨櫃位智慧排班系統", layout="wide")

SAVE_FILE = "staff_database.csv"
COLUMNS = ["員編", "姓名", "職稱", "劃休(/)", "補休(補)", "年假(年)", "國定假日(國)", "指定早(A)", "指定晚(B)"]

def mask_name(name):
    if len(name) <= 2: return name[0] + "O"
    return name[0] + "O" + name[2:]

def load_data():
    if os.path.exists(SAVE_FILE):
        try:
            df = pd.read_csv(SAVE_FILE, dtype=str).fillna("")
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            return df[COLUMNS]
        except Exception as e:
            return get_default_df()
    return get_default_df()

def get_default_df():
    raw_data = [
        {"員編": "800060", "姓名": "洪麗雯", "職稱": "資深經理"},
        {"員編": "800121", "姓名": "徐佩君", "職稱": "資深副理"},
        {"員編": "804280", "姓名": "鄭殷潔", "職稱": "副理"},
        {"員編": "802601", "姓名": "孫崇儀", "職稱": "主任"},
        {"員編": "804023", "姓名": "王莉文", "職稱": "主任"},
        {"員編": "805498", "姓名": "張語喬", "職稱": "資深組長"},
        {"員編": "808119", "姓名": "潘宛誼", "職稱": "資深專員"},
        {"員編": "808201", "姓名": "馬忠昀", "職稱": "資深專員"},
        {"員編": "809029", "姓名": "蕭婧仰", "職稱": "專員"},
        {"員編": "809183", "姓名": "林迪勝", "職稱": "專員"},
    ]
    df = pd.DataFrame(raw_data)
    for col in COLUMNS[3:]: df[col] = ""
    df["姓名"] = df["姓名"].apply(mask_name)
    return df

if 'staff_df' not in st.session_state:
    st.session_state.staff_df = load_data()

# --- CSS 樣式 ---
st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 14pt !important; }
    [data-testid="stDataEditor"] div { font-size: 14pt !important; color: #000000 !important; }
    th { background-color: #f8f9fa !important; color: #000000 !important; font-weight: bold !important; border: 1px solid #dee2e6 !important; }
    .stButton>button { font-size: 16pt !important; font-weight: bold; width: 100%; border-radius: 10px; height: 2.5em; }
    .rule-box { background-color: #fdfdfe; border-left: 5px solid #455a64; padding: 15px; border-radius: 5px; margin-bottom: 20px; color: #000000 !important; border: 1px solid #eceff1; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏬 百貨櫃位智慧排班系統")

# --- 人員資料編輯區 ---
st.sidebar.header("🗓️ 設定月份")
target_date = st.sidebar.date_input("選擇月份", datetime(2026, 3, 1))
target_month = target_date.replace(day=1)
num_days = ((target_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day

st.subheader("👥 人員資料與班次指派")
edited_df = st.data_editor(
    st.session_state.staff_df, 
    num_rows="dynamic", 
    use_container_width=True, 
    key="editor_v16",
    column_config={
        "劃休(/)": st.column_config.TextColumn("劃休(/)"),
        "補休(補)": st.column_config.TextColumn("補休(補)"),
        "年假(年)": st.column_config.TextColumn("年假(年)"),
        "國定假日(國)": st.column_config.TextColumn("國定假日(國)"),
        "指定早(A)": st.column_config.TextColumn("指定早(A)"),
        "指定晚(B)": st.column_config.TextColumn("指定晚(B)"),
        "員編": st.column_config.TextColumn("員編")
    }
)

if st.button("💾 儲存所有設定"):
    st.session_state.staff_df = edited_df.fillna("")
    st.session_state.staff_df.to_csv(SAVE_FILE, index=False)
    st.success("✅ 設定已儲存！")
    st.rerun()

# --- AI 核心邏輯 ---
def parse_days(s):
    if pd.isna(s) or str(s).strip() == "": return []
    clean = str(s).replace('.', ',').replace('，', ',')
    return [int(m.group(1)) for p in clean.split(',') if (m := re.search(r'(\d+)$', p.strip()))]

def generate_schedule(staff_df, start_date, days):
    model = cp_model.CpModel()
    names = staff_df["姓名"].tolist()
    dates = [start_date + timedelta(days=i) for i in range(days)]
    shifts = {(n, d, s): model.NewBoolVar(f's_{n}_{d}_{s}') for n in names for d in range(days) for s in [0,1,2]}
    objective_terms = []
    
    for _, row in staff_df.iterrows():
        n = row["姓名"]
        is_p1 = ("洪O雯" in n)
        is_p2 = ("潘O誼" in n)
        
        off_days = parse_days(row.get("劃休(/)", "")) + parse_days(row.get("補休(補)", "")) + \
                   parse_days(row.get("年假(年)", "")) + parse_days(row.get("國定假日(國)", ""))
        assign_A = parse_days(row.get("指定早(A)", ""))
        assign_B = parse_days(row.get("指定晚(B)", ""))

        for d in range(days):
            day_num = d + 1
            if day_num in off_days:
                if is_p1: model.Add(shifts[(n, d, 0)] == 1)
                else:
                    p = model.NewBoolVar(f'p_off_{n}_{d}')
                    model.Add(shifts[(n, d, 0)] == 1).OnlyEnforceIf(p)
                    objective_terms.append(p * (1000 if is_p2 else 100))
            else:
                if day_num in assign_A: model.Add(shifts[(n, d, 1)] == 1)
                if day_num in assign_B: model.Add(shifts[(n, d, 2)] == 1)

    for d in range(days):
        for n in names:
            model.Add(sum(shifts[(n, d, s)] for s in [0,1,2]) == 1)
            work = model.NewBoolVar(f'w_{n}_{d}')
            model.Add(sum(shifts[(n, d, s)] for s in [1, 2]) == 1).OnlyEnforceIf(work)
            objective_terms.append(work * 1)
        model.Add(sum(shifts[(n, d, 1)] for n in names) >= 2)
        model.Add(sum(shifts[(n, d, 2)] for n in names) >= 2)

    # === 排班健康規則 (加入洪O雯豁免特權) ===
    for n in names:
        is_p1 = ("洪O雯" in n)
        
        if not is_p1:
            # 一般同仁：套用嚴格的健康排班規則
            for d in range(days-1): 
                model.Add(shifts[(n,d,2)] + shifts[(n,d+1,1)] <= 1) # 晚不接早
            for d in range(days-4): 
                model.Add(sum(shifts[(n,d+i,s)] for i in range(5) for s in [1,2]) <= 4) # 連四休一
            model.Add(sum(shifts[(n,d,0)] for d in range(days)) >= 9) # 月休 9 天
        else:
            # 洪O雯：不在此限 (自由身)
            pass 

    model.Maximize(sum(objective_terms))
    solver = cp_model.CpSolver()
    if solver.Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        res = []
        for n in names:
            row_dict = staff_df[staff_df["姓名"]==n].iloc[0].to_dict()
            p_年 = parse_days(row_dict.get("年假(年)", "")); p_補 = parse_days(row_dict.get("補休(補)", ""))
            p_國 = parse_days(row_dict.get("國定假日(國)", ""))
            for d_idx, d_obj in enumerate(dates):
                h = f"{d_obj.month}/{d_obj.day}({['一','二','三','四','五','六','日'][d_obj.weekday()]})"
                day_num = d_idx + 1
                if solver.Value(shifts[(n,d_idx,1)]): v="A"
                elif solver.Value(shifts[(n,d_idx,2)]): v="B1"
                else:
                    if day_num in p_年: v="年"
                    elif day_num in p_補: v="補"
                    elif day_num in p_國: v="國"
                    else: v="/"
                row_dict[h] = v
            res.append(row_dict)
        return pd.DataFrame(res)
    return None

# --- 🚀 執行區 ---
st.markdown("---")
if st.button("🚀 執行 AI 智慧排班"):
    final_df = generate_schedule(edited_df, target_month, num_days)
    if final_df is not None:
        st.success("✅ 班表生成成功！(已套用洪O雯特殊豁免權)")
        st.data_editor(final_df, use_container_width=True, height=550)
        st.download_button("📥 下載 CSV", final_df.to_csv(index=False).encode('utf-8-sig'), "Schedule.csv")
    else:
        st.error("🚨 條件衝突，請確認其他同仁的人力分配。")
