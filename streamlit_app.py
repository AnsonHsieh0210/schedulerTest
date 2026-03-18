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
                if col not in df.columns: df[col] = ""
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

st.title("🏬 百貨櫃位智慧排班系統 (做三休一版)")

# --- 人員資料編輯區 ---
st.sidebar.header("🗓️ 設定月份")
target_date = st.sidebar.date_input("選擇月份", datetime(2026, 4, 1))
target_month = target_date.replace(day=1)
num_days = ((target_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day

st.subheader("👥 人員資料與班次指派")
edited_df = st.data_editor(
    st.session_state.staff_df, 
    num_rows="dynamic", 
    use_container_width=True, 
    key="editor_v25",
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
    month = start_date.month
    dates = [start_date + timedelta(days=i) for i in range(days)]
    shifts = {(n, d, s): model.NewBoolVar(f's_{n}_{d}_{s}') for n in names for d in range(days) for s in [0,1,2]}
    objective_terms = []
    
    manual_A_all = {}
    manual_B_all = {}
    
    for _, row in staff_df.iterrows():
        n = row["姓名"]
        is_p1 = ("洪O雯" in n)
        is_p2 = ("潘O誼" in n)
        
        off_days = parse_days(row.get("劃休(/)", "")) + parse_days(row.get("補休(補)", "")) + \
                   parse_days(row.get("年假(年)", "")) + parse_days(row.get("國定假日(國)", ""))
        assign_A = parse_days(row.get("指定早(A)", ""))
        assign_B = parse_days(row.get("指定晚(B)", ""))
        
        manual_A_all[n] = assign_A
        manual_B_all[n] = assign_B

        for d in range(days):
            day_num = d + 1
            if day_num in assign_A: 
                model.Add(shifts[(n, d, 1)] == 1)
            elif day_num in assign_B: 
                model.Add(shifts[(n, d, 2)] == 1)
            elif day_num in off_days:
                if is_p1: model.Add(shifts[(n, d, 0)] == 1)
                else:
                    p = model.NewBoolVar(f'p_off_{n}_{d}')
                    model.Add(shifts[(n, d, 0)] == 1).OnlyEnforceIf(p)
                    objective_terms.append(p * (2000 if is_p2 else 200))

    # === 動態區間人力門檻 (目標 5A3B，保底 3A2B) ===
    for d in range(days):
        day_num = d + 1
        
        min_A, max_A = 3, 5
        min_B, max_B = 2, 3 
        
        if month == 4:
            if day_num in [4, 5]:
                min_B, max_B = 3, 3 

            if day_num == 13:
                max_A, max_B = 10, 10
                for n in names:
                    if not ("洪O雯" in n) and day_num not in manual_A_all[n] and day_num not in manual_B_all[n]:
                        model.Add(shifts[(n, d, 0)] == 0)

            if day_num in [7, 21]:
                banned_1 = ["徐O君", "鄭O潔", "孫O儀", "王O文", "張O喬"]
                for n in names:
                    if any(b in n for b in banned_1) and not ("洪O雯" in n):
                        if day_num not in manual_A_all[n] and day_num not in manual_B_all[n]:
                            model.Add(shifts[(n, d, 0)] == 0)

        day_manual_A_count = sum(1 for n in names if day_num in manual_A_all[n])
        day_manual_B_count = sum(1 for n in names if day_num in manual_B_all[n])
        max_A = max(max_A, day_manual_A_count)
        max_B = max(max_B, day_manual_B_count)

        for n in names:
            model.Add(sum(shifts[(n, d, s)] for s in [0,1,2]) == 1)
            # 鼓勵排早晚班朝 5A3B 邁進
            objective_terms.append(shifts[(n, d, 1)] * 3) 
            objective_terms.append(shifts[(n, d, 2)] * 2) 
        
        model.Add(sum(shifts[(n, d, 1)] for n in names) >= min_A)
        model.Add(sum(shifts[(n, d, 1)] for n in names) <= max_A)
        model.Add(sum(shifts[(n, d, 2)] for n in names) >= min_B)
        model.Add(sum(shifts[(n, d, 2)] for n in names) <= max_B)

    # === 排班健康規則 & 早晚班平均 & 洪/徐早班特權 ===
    for n in names:
        is_p1 = ("洪O雯" in n)
        is_xu = ("徐O君" in n)
        assigned_all = set(manual_A_all[n] + manual_B_all[n])
        
        # 洪O雯、徐O君：極度偏好早班
        if is_p1 or is_xu:
            for d in range(days):
                objective_terms.append(shifts[(n, d, 1)] * 10) 
        
        if not is_p1:
            for d in range(days-1): 
                if (d+1) in manual_B_all[n] and (d+2) in manual_A_all[n]: pass 
                else: model.Add(shifts[(n,d,2)] + shifts[(n,d+1,1)] <= 1)
            
            # --- 關鍵修改：做三休一防護網 ---
            for d in range(days-3): 
                # 若手動強制連上4天則放行，否則強制在任何連續 4 天內，上班日不得超過 3 天
                if sum(1 for i in range(4) if (d+i+1) in assigned_all) == 4: pass
                else: model.Add(sum(shifts[(n,d+i,s)] for i in range(4) for s in [1,2]) <= 3)
            
            # 月休 11 天鐵律
            required_offs = 11 if month == 4 else 9
            actual_req_offs = min(required_offs, days - len(assigned_all))
            if actual_req_offs > 0:
                model.Add(sum(shifts[(n,d,0)] for d in range(days)) >= actual_req_offs)
            
        # 其他人的早晚班平均 (排除洪、徐)
        if not (is_p1 or is_xu):
            total_A = sum(shifts[(n, d, 1)] for d in range(days))
            total_B = sum(shifts[(n, d, 2)] for d in range(days))
            diff = model.NewIntVar(-days, days, f'diff_{n}')
            model.Add(diff == total_A - total_B)
            abs_diff = model.NewIntVar(0, days, f'abs_diff_{n}')
            model.AddAbsEquality(abs_diff, diff)
            objective_terms.append(abs_diff * -15) 

        # 防碎班邏輯 (仍保留，避免單日孤立班)
        for d in range(1, days - 1):
            iso_work = model.NewBoolVar(f'iso_work_{n}_{d}')
            model.AddBoolOr([shifts[(n, d-1, 0)].Not(), shifts[(n, d, 0)], shifts[(n, d+1, 0)].Not(), iso_work])
            objective_terms.append(iso_work * -30)

            iso_off = model.NewBoolVar(f'iso_off_{n}_{d}')
            model.AddBoolOr([shifts[(n, d-1, 0)], shifts[(n, d, 0)].Not(), shifts[(n, d+1, 0)], iso_off])
            objective_terms.append(iso_off * -30)

    model.Maximize(sum(objective_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0 
    
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
st.markdown("#### 📅 智慧排班機制說明：")
st.info("⭐ **做三休一防護網**：系統限制每位同仁連續上班不得超過 3 天（手動指派除外）。\n⭐ **目標 5A3B (保底 3A2B)**：自動最大化每日人力配置。")

if st.button("🚀 執行 AI 智慧排班"):
    final_df = generate_schedule(edited_df, target_month, num_days)
    if final_df is not None:
        st.success("✅ 班表生成成功！已成功套用『做三休一』之排班防護。")
        st.data_editor(final_df, use_container_width=True, height=550)
        st.download_button("📥 下載 CSV", final_df.to_csv(index=False).encode('utf-8-sig'), "Schedule.csv")
    else:
        st.error("🚨 條件衝突：『做三休一』規則大幅增加了排班難度，若顯示此錯誤，請嘗試減少同仁在假日前後的劃休天數。")
