import streamlit as st
import pandas as pd
import re
import requests
from io import BytesIO, StringIO
from datetime import date

# --- 1. Excel変換用補助関数 ---
def time_to_excel_serial(time_str):
    """'13:30' を Excelのシリアル値に変換"""
    if not time_str or ':' not in str(time_str):
        return None
    try:
        h, m = map(int, str(time_str).split(':'))
        return (h / 24.0) + (m / 1440.0)
    except:
        return None

# --- 2. 共通のデータ変換関数 ---
def transform_data(df):
    df.columns = [f"Column{i+1}" for i in range(len(df.columns))]
    df = df.astype(str).apply(lambda x: x.str.strip())
    df = df.replace(['nan', 'None', ''], '')

    def extract_year(text):
        match = re.search(r'和\s*(\d+)', str(text))
        return int(match.group(1)) + 2018 if match else None

    df['year_val'] = df['Column1'].apply(extract_year)
    df['year_val'] = df['year_val'].replace('', None).ffill()

    df['氏名'] = df.apply(lambda x: x['Column2'] if "氏名" in str(x['Column1']) else None, axis=1)
    df['乗務員コード'] = df.apply(lambda x: x['Column4'] if "コード" in str(x['Column3']) else None, axis=1)
    df[['氏名', '乗務員コード']] = df[['氏名', '乗務員コード']].replace('', None).ffill()

    def create_date(row):
        text = str(row['Column1'])
        match = re.search(r'(\d+)月\s*(\d+)日', text)
        if match and pd.notnull(row['year_val']):
            try:
                # 確実に datetime オブジェクトにする
                return pd.to_datetime(date(int(row['year_val']), int(match.group(1)), int(match.group(2))))
            except:
                return None
        return None

    df['日付'] = df.apply(create_date, axis=1)

    ignore_keywords = ["累計拘束時間", "D2 :", "最大拘束時間", "事業所", "令和", "日付", "氏名"]
    df = df[df['日付'].notnull()]
    for kw in ignore_keywords:
        df = df[~df['Column1'].str.contains(kw, na=False)]

    rename_dict = {
        "Column2": "始業時刻", "Column3": "終業時刻", "Column4": "運転時間",
        "Column5": "重複運転時間", "Column6": "荷役時間", "Column7": "重複荷役時間",
        "Column8": "休憩時間", "Column9": "重複休憩時間", "Column10": "拘束時間小計",
        "Column11": "重複拘束時間小計", "Column12": "拘束時間合計", "Column13": "拘束時間累計",
        "Column14": "前運転平均", "Column15": "後運転平均", "Column16": "休息時間",
        "Column17": "実働時間", "Column18": "時間外時間", "Column19": "深夜時間",
        "Column20": "時間外深夜時間", "Column21": "摘要1", "Column22": "摘要2"
    }
    df = df.rename(columns=rename_dict)
    final_cols = ["乗務員コード", "氏名", "日付"] + [c for c in rename_dict.values() if c in df.columns]
    return df[final_cols]

# --- 3. Streamlit Web画面 ---
st.set_page_config(page_title="拘束時間管理変換ツール", layout="wide")
st.title("🚛 拘束時間管理表 変換ツール")

uploaded_file = st.file_uploader("ここにCSVファイルをドロップしてください", type="csv")
processed_df = None

if uploaded_file:
    df_input = pd.read_csv(
        uploaded_file,
        encoding='cp932',
        header=None,
        engine='python',
        on_bad_lines='skip'
    )
    if len(df_input.columns) > 22:
        df_input = df_input.iloc[:, :22]
        df_input.columns = range(len(df_input.columns))
    
    # デバッグ用
    st.write(f"読み込み行数: {len(df_input)}")
    st.write(f"列数: {len(df_input.columns)}")
    st.dataframe(df_input.head(10))
    
    processed_df = transform_data(df_input)

if processed_df is not None:
    st.divider()
    st.subheader("✅ 変換完了プレビュー")
    # プレビュー表示用
    display_df = processed_df.copy()
    display_df['日付'] = display_df['日付'].dt.strftime('%Y/%m/%d')
    st.dataframe(display_df, use_container_width=True)

    # --- Excelダウンロード ---
    st.divider()
    output = BytesIO()
    try:
        export_df = processed_df.copy()
        time_cols = [
            "始業時刻", "終業時刻", "運転時間", "重複運転時間", "荷役時間", 
            "重複荷役時間", "休憩時間", "重複休憩時間", "拘束時間小計", 
            "重複拘束時間小計", "拘束時間合計", "拘束時間累計", "休息時間", 
            "実働時間", "時間外時間", "深夜時間", "時間外深夜時間"
        ]
        
        for col in time_cols:
            if col in export_df.columns:
                export_df[col] = export_df[col].apply(time_to_excel_serial)

        # 🌟 ポイント: datetime_format を空にしてデフォルトを無効化
        with pd.ExcelWriter(output, engine='xlsxwriter', datetime_format='') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Sheet1')
            workbook = writer.book
            worksheet = writer.sheets['Sheet1']
            
            # フォーマット定義
            h_mm_format = workbook.add_format({'num_format': '[h]:mm', 'align': 'right'})
            # yyyy/m/d とすることで 2025/1/2 のように表示
            date_format = workbook.add_format({'num_format': 'yyyy/m/d', 'align': 'left'})
            
            for i, col_name in enumerate(export_df.columns):
                if col_name == "日付":
                    worksheet.set_column(i, i, 15, date_format)
                elif col_name in time_cols:
                    worksheet.set_column(i, i, 12, h_mm_format)
                else:
                    worksheet.set_column(i, i, 15)

        st.download_button(
            label="📥 計算用Excelをダウンロード",
            data=output.getvalue(),
            file_name=f"拘束時間管理表_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Excel作成エラー: {e}")





