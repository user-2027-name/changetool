import streamlit as st
import pandas as pd
import re
import requests
from io import BytesIO, StringIO
from datetime import date

# --- 1. 計算用の関数 (表には出さず、計算が必要な時だけ呼び出す) ---
def time_to_num(time_str):
    """'13:30' を 13.5 に変換する"""
    if not time_str or ':' not in str(time_str):
        return 0.0
    try:
        h, m = map(int, str(time_str).split(':'))
        return round(h + (m / 60.0), 2)
    except:
        return 0.0

def num_to_time(total_hours):
    """13.5 を '13:30' に戻す"""
    h = int(total_hours)
    m = int(round((total_hours - h) * 60))
    return f"{h}:{m:02d}"

# --- 2. 共通のデータ変換関数 ---
def transform_data(df):
    # 列名の初期設定 (22列固定)
    df.columns = [f"Column{i+1}" for i in range(len(df.columns))]
    
    # 型の統一とトリミング
    df = df.astype(str).apply(lambda x: x.str.strip())
    df = df.replace(['nan', 'None', ''], '')

    # 和暦(年)の抽出と西暦変換
    def extract_year(text):
        match = re.search(r'和\s*(\d+)', str(text))
        return int(match.group(1)) + 2018 if match else None

    df['year_val'] = df['Column1'].apply(extract_year)
    df['year_val'] = df['year_val'].replace('', None).ffill()

    # 氏名と乗務員コードの抽出
    df['氏名'] = df.apply(lambda x: x['Column2'] if "氏名" in str(x['Column1']) else None, axis=1)
    df['乗務員コード'] = df.apply(lambda x: x['Column4'] if "コード" in str(x['Column3']) else None, axis=1)
    df[['氏名', '乗務員コード']] = df[['氏名', '乗務員コード']].replace('', None).ffill()

    # 日付作成
    def create_date(row):
        text = str(row['Column1'])
        match = re.search(r'(\d+)月\s*(\d+)日', text)
        if match and pd.notnull(row['year_val']):
            try:
                d = date(int(row['year_val']), int(match.group(1)), int(match.group(2)))
                return d.strftime('%Y/%m/%d')
            except:
                return ""
        return ""

    df['日付'] = df.apply(create_date, axis=1)

    # 不要な行の削除
    ignore_keywords = ["累計拘束時間", "D2 :", "最大拘束時間", "事業所", "令和", "日付", "氏名"]
    df = df[df['日付'] != ""]
    for kw in ignore_keywords:
        df = df[~df['Column1'].str.contains(kw, na=False)]

    # リネーム
    rename_dict = {
        "Column2": "始業時刻", "Column3": "終業時刻", "Column4": "運転時間",
        "Column8": "休憩時間", "Column12": "拘束時間合計", "Column17": "実働時間"
    }
    df = df.rename(columns=rename_dict)
    
    final_cols = ["乗務員コード", "氏名", "日付"] + [c for c in rename_dict.values() if c in df.columns]
    return df[final_cols].replace(['nan', 'None', None], '')

# --- 3. Streamlit Web画面 ---
st.set_page_config(page_title="拘束時間管理変換ツール", layout="wide")
st.title("🚛 拘束時間管理表 変換ツール")

tab1, tab2 = st.tabs(["📤 CSVファイルをD&D", "🌐 APIから取得"])

processed_df = None

with tab1:
    uploaded_file = st.file_uploader("ここにCSVファイルをドロップしてください", type="csv")
    if uploaded_file:
        df_input = pd.read_csv(uploaded_file, encoding='cp932', header=None, names=range(22), engine='python')
        processed_df = transform_data(df_input)

with tab2:
    api_url = st.text_input("API URL", value="")
    if st.button("APIを実行"):
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            df_input = pd.read_csv(StringIO(response.text), header=None, names=range(22), engine='python')
            processed_df = transform_data(df_input)
            st.success("API取得成功！")
        except Exception as e:
            st.error(f"APIエラー: {e}")

# --- 4. プレビューと集計・ダウンロード ---
if processed_df is not None:
    st.divider()
    st.subheader("✅ 変換完了プレビュー")
    st.dataframe(processed_df, use_container_width=True)

    # --- 集計処理 (裏側で計算) ---
    st.subheader("📊 実働時間の集計")
    target_col = "実働時間"
    if target_col in processed_df.columns:
        # 数値に変換して合計を出す
        total_hours = processed_df[target_col].apply(time_to_num).sum()
        # 表示用に 'XX:XX' 形式に戻す
        total_time_str = num_to_time(total_hours)

        c1, c2 = st.columns(2)
        c1.metric(f"全体の{target_col} 合計", total_time_str)
        c2.metric("数値換算（合計時間）", f"{total_hours:.2f} h")
    
    # --- Excelダウンロード ---
    st.divider()
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            processed_df.to_excel(writer, index=False, sheet_name='Sheet1')
        
        st.download_button(
            label="📥 変換済みExcelをダウンロード",
            data=output.getvalue(),
            file_name=f"拘束時間管理表_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Excel作成エラー: {e}")
